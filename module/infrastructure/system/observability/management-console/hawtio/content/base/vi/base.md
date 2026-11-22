# Observability Management Console Hawtio

Hawtio là giao diện web để quan sát và quản lý ứng dụng Java đang chạy. Thông qua JMX, các MBean và Jolokia, Hawtio cho phép xem thuộc tính runtime, theo dõi biểu đồ và thực hiện những thao tác quản trị được ứng dụng công bố. Hệ thống plugin giúp hiển thị thêm thông tin theo công nghệ, chẳng hạn Apache Camel, Spring Boot hoặc Quartz.

Module này dành cho lập trình viên Java và người vận hành đã biết khái niệm JVM nhưng muốn sử dụng một console thực tế để kiểm tra trạng thái ứng dụng. Trọng tâm là hiểu đường đi từ giao diện Hawtio đến JVM, kết nối an toàn, đọc đúng dữ liệu JMX và phân biệt thao tác quan sát với thao tác có thể thay đổi trạng thái hệ thống.

Lộ trình đi từ vai trò và kiến trúc Hawtio đến cài đặt, kết nối JVM, khám phá MBean, theo dõi runtime và sử dụng plugin. Phần cuối hướng dẫn cấu hình quyền truy cập, giới hạn kết nối và thực hành chẩn đoán dựa trên chỉ số, biểu đồ cùng dữ liệu có sẵn trong console.