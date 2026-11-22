# Observability Alerting Prometheus Rules

Prometheus Alerting Rules cho phép chuyển dữ liệu metrics thành tín hiệu cảnh báo bằng biểu thức PromQL được đánh giá định kỳ. Khi điều kiện thỏa, cảnh báo có thể ở trạng thái `pending` rồi `firing`; Prometheus chuyển cảnh báo tới Alertmanager để xử lý thông báo.

Module dành cho người đã biết metrics và PromQL cơ bản, muốn xây dựng cảnh báo hữu ích cho dịch vụ đang vận hành. Nội dung tập trung vào cấu trúc YAML của rule, điều kiện và thời gian kích hoạt, nhãn/annotation, tổ chức nhóm rule, kiểm thử và kiểm soát nhiễu; cấu hình thông báo chi tiết thuộc phần Alertmanager.

Lộ trình gồm tám mốc ngắn, đi từ luồng cảnh báo và khai báo rule tới xác minh bằng `promtool` và đánh giá chất lượng. Hoàn thành module, bạn có thể viết và kiểm thử một bộ alerting rules rõ ràng, phù hợp ngữ cảnh vận hành.