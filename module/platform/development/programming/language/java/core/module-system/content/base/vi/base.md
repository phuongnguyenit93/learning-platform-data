# Java Core — Module System

Java Platform Module System (JPMS), được giới thiệu từ Java 9, tổ chức chương trình thành các module có tên, phụ thuộc được khai báo tường minh và ranh giới API rõ ràng. Khác với việc chỉ nhóm lớp vào package, JPMS giúp kiểm soát module nào được đọc, package nào được xuất ra ngoài và khi nào có thể dùng reflection.

Module học này dành cho người đã quen với class, package và cách chạy chương trình Java. Bạn sẽ tìm hiểu `module-info.java`, các dạng `requires`, quy tắc `exports`/`opens`, cơ chế service, cách biên dịch và chạy trên module path, tương thích với JAR cũ, rồi phân tích phụ thuộc bằng `jdeps` và tạo runtime image bằng `jlink`. Sau lộ trình, bạn có thể chia một ứng dụng Java nhỏ thành các module có API rõ ràng, chạy được và dễ quản lý phụ thuộc.