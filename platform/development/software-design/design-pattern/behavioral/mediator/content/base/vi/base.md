# Software Design Design Pattern Behavioral Mediator

Mediator là một mẫu thiết kế hành vi giúp các đối tượng cộng tác mà không phụ thuộc trực tiếp vào nhau. Khi nhiều thành phần cùng gọi và theo dõi lẫn nhau, mạng quan hệ chằng chịt khiến việc sửa đổi, kiểm thử và tái sử dụng trở nên khó khăn. Thay vì để mỗi thành phần biết mọi thành phần khác, Mediator đóng vai trò trung gian tiếp nhận yêu cầu hoặc sự kiện và điều phối tương tác theo các quy tắc chung.

Lộ trình một cấp gồm tám mốc: bắt đầu từ bài toán coupling, làm rõ trách nhiệm của Mediator và Colleague, xây dựng interface và ConcreteMediator, rồi tổ chức các thông báo từ Colleague. Sau đó, người học refactor những lời gọi trực tiếp thành giao tiếp gián tiếp, so sánh Mediator với Observer và Facade, nhận diện nguy cơ tạo God Object và kiểm thử những luồng phối hợp giữa các thành phần.

Module phù hợp với người đã biết lập trình hướng đối tượng, interface, đa hình và quan hệ giữa các lớp. Sau khi hoàn thành, bạn có thể nhận diện bối cảnh nên dùng Mediator, thiết kế một ví dụ Java nhỏ cho các thành phần tương tác, giảm coupling có kiểm soát và viết kiểm thử chứng minh hành vi điều phối vẫn đúng khi từng thành phần thay đổi.