# Observability Instrumentation với OpenTelemetry

OpenTelemetry (OTel) là bộ chuẩn và công cụ mã nguồn mở giúp ứng dụng phát sinh, xử lý và xuất dữ liệu quan sát như traces, metrics và logs. Module này tập trung vào cách instrument ứng dụng Java/Spring Boot để hiểu đường đi của yêu cầu, hiệu năng và lỗi mà không bị ràng buộc vào một hệ thống quan sát cụ thể.

Bạn sẽ đi từ kiến trúc API, SDK và Resource đến auto instrumentation bằng Java Agent, rồi tự bổ sung span và metric cho nghiệp vụ. Sau đó, bạn học cách liên kết log với trace, duy trì context giữa các dịch vụ, tuân thủ semantic conventions và gửi dữ liệu qua OTLP đến Collector.

Kết thúc lộ trình, bạn có thể thiết lập một luồng telemetry cơ bản, đối chiếu trace–metric–log khi xử lý sự cố và đánh giá các yếu tố vận hành như sampling, chi phí thu thập, dữ liệu nhạy cảm và telemetry trùng lặp.