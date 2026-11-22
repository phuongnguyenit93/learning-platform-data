# Observability Telemetry Governance Data Classification

Dữ liệu observability từ logs, metrics và traces giúp tìm hiểu hoạt động của hệ thống, nhưng payload, nhãn và thuộc tính của chúng có thể chứa thông tin cá nhân, bí mật hoặc dữ liệu nghiệp vụ nhạy cảm. Data Classification là quá trình nhận diện và xác định mức bảo vệ phù hợp cho từng loại dữ liệu theo nội dung, ngữ cảnh và rủi ro khi bị lộ hoặc sử dụng sai.

Module dành cho developer, DevOps, SRE và người phụ trách quản trị dữ liệu telemetry. Lộ trình đi từ nhận diện các nguồn và trường dữ liệu, xác lập tiêu chí và mức độ nhạy cảm, phát hiện PII và secrets, đến việc gắn nhãn phân loại theo trường. Các mức như Public, Internal, Confidential và Restricted chỉ là ví dụ; hệ phân loại thực tế cần tuân theo chính sách của tổ chức.

Sau khi học, bạn có thể phân loại một mẫu log, metric hoặc trace, giải thích lý do gắn nhãn, xác định yêu cầu bảo vệ tương ứng như che dữ liệu, phân quyền và lưu giữ, rồi rà soát các ngoại lệ khi schema thay đổi. Đây là nền tảng cho các bước quản trị telemetry tiếp theo, gồm data minimization, filtering, masking và redaction.