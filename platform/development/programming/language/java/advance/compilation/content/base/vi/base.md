# Java Advance - Compilation

Module này giúp bạn hiểu và kiểm soát quá trình biên dịch Java: từ tệp mã nguồn `.java` đến tệp `.class` dùng làm đầu vào cho JVM. Trọng tâm là trình biên dịch `javac`, các kiểm tra trước khi chạy, cách tìm phụ thuộc và việc tạo đầu ra phù hợp với phiên bản Java đích. Việc nạp lớp và JIT được đặt đúng vị trí trong bức tranh chung để tránh nhầm chúng với biên dịch mã nguồn.

Nội dung dành cho người đã nắm cú pháp Java, lớp, package và cách chạy chương trình cơ bản. Lộ trình bắt đầu bằng luồng biên dịch và thao tác với `javac`, sau đó đi qua lỗi/cảnh báo, classpath và module path, rồi đến tương thích phiên bản. Từ nền tảng đó, bạn tìm hiểu sinh mã qua annotation processing, gọi trình biên dịch bằng `JavaCompiler` và kiểm chứng kết quả bằng `javap`.

Tư duy xuyên suốt là xem một lần biên dịch như một quá trình có đầu vào, cấu hình, chẩn đoán và đầu ra có thể kiểm tra. Sau khi học, bạn có thể giải thích vì sao mã biên dịch thành công hoặc thất bại, cấu hình môi trường biên dịch rõ ràng và kiểm tra tệp class thay vì chỉ dựa vào thông báo thành công của IDE.
