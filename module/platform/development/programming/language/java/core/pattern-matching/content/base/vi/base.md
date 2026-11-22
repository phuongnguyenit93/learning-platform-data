# Java Core Pattern Matching

Pattern matching trong Java cho phép kiểm tra kiểu hoặc cấu trúc của một giá trị, đồng thời lấy ra các phần dữ liệu cần dùng khi khớp mẫu. Nhờ đó, mã xử lý các kiểu đối tượng khác nhau trở nên gọn và rõ hơn, giảm thao tác ép kiểu thủ công. Module tập trung vào các tính năng ổn định của Java 21: type patterns với `instanceof`, pattern matching trong `switch` và record patterns.

Nội dung dành cho người học đã nắm Java cơ bản, kế thừa, interface, `switch` và khái niệm record. Lộ trình bắt đầu bằng pattern variable và phạm vi của biến, tiếp đến là rẽ nhánh theo kiểu đối tượng bằng `switch`, điều kiện `when`, xử lý `null`, quy tắc dominance và yêu cầu exhaustiveness. Phần record patterns hướng dẫn bóc tách dữ liệu, gồm cả các record lồng nhau.

Ở phần thực hành, bạn sẽ chuyển một số đoạn `if/else` cùng phép ép kiểu thành pattern matching, biên dịch và kiểm tra lại hành vi. Hoàn thành module, bạn có thể chọn mẫu phù hợp, hiểu các lỗi biên dịch phổ biến liên quan đến phạm vi và thứ tự nhánh, đồng thời viết mã phân nhánh Java dễ bảo trì hơn.