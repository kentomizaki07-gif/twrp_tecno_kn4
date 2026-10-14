$(call inherit-product, $(SRC_TARGET_DIR)/product/base.mk)
$(call inherit-product, $(SRC_TARGET_DIR)/product/core_64_bit_only.mk)
$(call inherit-product, $(SRC_TARGET_DIR)/product/virtual_ab_ota/compression.mk)
$(call inherit-product, vendor/twrp/config/common.mk)

PRODUCT_NAME := twrp_KN4
PRODUCT_DEVICE := KN4
PRODUCT_BRAND := TECNO
PRODUCT_MODEL := TECNO KN4
PRODUCT_MANUFACTURER := TECNO
PRODUCT_USE_DYNAMIC_PARTITIONS := true
PRODUCT_VIRTUAL_AB_OTA := true
PRODUCT_PACKAGES += update_engine_sideload
PRODUCT_COPY_FILES += $(call find-copy-subdir-files,*,device/tecno/KN4/recovery/root/,recovery/root/)
