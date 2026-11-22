# E2E Test — Kiểm thử đầu cuối

E2E (End-to-End) Test kiểm chứng một hành trình nghiệp vụ hoàn chỉnh từ góc nhìn người dùng hoặc hệ thống gọi, qua các thành phần thực sự tham gia xử lý. Mục tiêu là xác nhận những luồng quan trọng vẫn hoạt động đúng khi ứng dụng, dịch vụ, cơ sở dữ liệu và các điểm tích hợp phối hợp với nhau.

Module tập trung vào **phạm vi kiểm thử E2E**: lựa chọn hành trình có giá trị và rủi ro cao, thiết kế kịch bản cùng tiêu chí đạt, chuẩn bị môi trường và dữ liệu, kiểm tra kết quả xuyên hệ thống, hạn chế test không ổn định và vận hành bộ kiểm thử trong CI. Kiểm thử E2E thường tốn thời gian và chi phí bảo trì hơn các kiểm thử tầng thấp, vì vậy cần chọn đúng các hành trình cốt lõi.

Người học nên có kiến thức cơ bản về kiểm thử phần mềm, HTTP/API và luồng hoạt động của ứng dụng. Sau module, bạn có thể xây dựng một bộ smoke E2E nhỏ, độc lập, dễ chẩn đoán và đủ sức cảnh báo khi những hành trình nghiệp vụ thiết yếu gặp sự cố.