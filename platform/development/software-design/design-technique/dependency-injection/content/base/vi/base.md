# Software Design Design Technique Dependency Injection

Dependency Injection (DI) là kỹ thuật thiết kế trong đó một đối tượng nhận các thành phần mà nó cần từ bên ngoài, thay vì tự quyết định cách khởi tạo chúng. Nhờ tách việc sử dụng khỏi việc lắp ghép dependency, mã nguồn dễ thay thế implementation, kiểm thử độc lập và điều chỉnh cấu hình hơn. DI có thể thực hiện bằng Java thuần, không nhất thiết phải bắt đầu bằng một framework.

Lộ trình gồm tám mốc: nhận diện phụ thuộc và coupling, hiểu IoC/DI, chọn constructor hoặc setter injection, thiết kế hợp đồng phù hợp, tập trung cấu hình tại composition root, sử dụng DI container, kiểm soát scope/vòng đời và cuối cùng là kiểm thử cùng các thực hành cần tránh. Các ví dụ dùng Java và có thể mở rộng sang Spring hoặc Guice để minh họa cơ chế tự động nối các đối tượng.

Module phù hợp với lập trình viên đã biết class, interface, constructor và unit testing cơ bản. Sau khi hoàn thành, bạn có thể tái cấu trúc một lớp đang gắn cứng với implementation, tự lắp ghép object graph hoặc cấu hình container, kiểm tra vòng đời dependency và viết bài kiểm thử bằng fake/mock mà không phụ thuộc vào toàn bộ ứng dụng.