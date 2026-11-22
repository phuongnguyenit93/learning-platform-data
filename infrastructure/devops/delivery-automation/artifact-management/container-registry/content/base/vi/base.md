# DevOps Delivery Automation Artifact Management Container Registry

Container Registry là hệ thống lưu trữ và phân phối container image để các môi trường build, kiểm thử và triển khai sử dụng cùng một artifact. Module **DevOps Delivery Automation Artifact Management Container Registry** tập trung vào cách tổ chức image theo chuẩn OCI, quản lý tên và phiên bản, kiểm soát quyền truy cập và kết nối registry với quy trình phân phối phần mềm.

Lộ trình gồm tám mốc: nền tảng OCI và registry, tags/digests, thao tác push/pull, xác thực/phân quyền, tích hợp CI/CD, bảo mật chuỗi cung ứng, quản lý vòng đời và vận hành triển khai. Người học sẽ đi từ xuất bản một image đơn giản đến việc chọn đúng artifact theo digest, xác minh nguồn gốc và thiết lập chính sách bảo quản bản phát hành.

Module phù hợp với lập trình viên và kỹ sư DevOps đã biết Docker cùng kiến thức Git, build và CI cơ bản. Sau khi hoàn thành, bạn có thể thiết kế quy ước lưu trữ image, tự động hóa publish, bảo vệ registry private, phân biệt tag với digest và kiểm soát việc sử dụng artifact trong release hoặc rollback.