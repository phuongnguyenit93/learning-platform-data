# Java Core JDK Tooling

JDK (Java Development Kit) không chỉ cung cấp trình biên dịch và môi trường chạy Java mà còn có các công cụ để thử nghiệm mã, đóng gói, phân tích phụ thuộc và chẩn đoán JVM. Module này giúp bạn hiểu vai trò của từng lệnh JDK và thực hành một quy trình hoàn chỉnh từ tệp `.java` đến ứng dụng có thể chạy, kiểm tra và phân phối.

Người học nên biết Java cơ bản và thao tác terminal. Lộ trình bắt đầu bằng kiểm tra phiên bản JDK, cấu hình môi trường, biên dịch với `javac` và chạy bằng `java`. Sau đó, bạn dùng `jshell` để thử ý tưởng, `jar` và `javadoc` để đóng gói và tạo tài liệu, `javap` cùng `jdeps` để phân tích chương trình, rồi làm quen `jlink`, `jpackage` và các công cụ chẩn đoán như `jcmd` hoặc Java Flight Recorder.

Khi hoàn thành, bạn có thể tự biên dịch, chạy, kiểm tra và đóng gói một ứng dụng Java bằng các công cụ chuẩn có sẵn trong JDK, nhận diện lỗi cấu hình classpath/phiên bản, và thu thập thông tin ban đầu khi JVM gặp vấn đề. Cú pháp và tính sẵn có của một số tùy chọn phụ thuộc phiên bản JDK và hệ điều hành.