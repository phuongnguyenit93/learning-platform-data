# Khi nào record pattern làm code rõ hơn?

**Áp dụng:** Java 21 trở lên. Record pattern được chuẩn hóa trong Java 21 (JEP 440), không cần bật preview. Java 17 có kiểu record nhưng chưa hỗ trợ cú pháp record pattern.

## 1. Mục tiêu: nói rõ dữ liệu cần lấy ngay tại chỗ kiểm tra kiểu

Một record mô tả một nhóm thành phần dữ liệu. Khi một biến có kiểu tổng quát (chẳng hạn Object), ta thường phải kiểm tra kiểu, lấy đối tượng đã ép kiểu, rồi gọi từng accessor.

Với record pattern, ta diễn tả cả **kiểu record** lẫn **các thành phần cần lấy** trong cùng một mẫu. Ví dụ, với hai record sau:

~~~java
record Point(int x, int y) {}
record Segment(Point start, Point end) {}
~~~

- Mẫu **Point(int x, int y)** kiểm tra giá trị có phải Point hay không và, nếu khớp, đặt hai thành phần vào biến x, y.
- Mẫu **Segment(Point(int startX, int startY), Point(int endX, int endY))** đi thêm một cấp: lấy tọa độ của cả hai đầu đoạn thẳng.
- Đây là **cú pháp so khớp và giải cấu trúc**, không phải lời gọi constructor; nó không tạo một Point hay Segment mới.

**Quy tắc nhận biết nhanh:** record pattern đáng dùng khi một nhánh xử lý cần nhiều thành phần của cùng một record, đặc biệt khi có record lồng nhau, và hình dạng dữ liệu giúp người đọc hiểu nhánh đó.

## 2. Trước và sau: giảm thao tác trung gian mà vẫn giữ ý nghĩa

Giả sử cần định dạng tọa độ của một Segment. Một Segment chỉ được xem là đầy đủ khi cả start và end đều là Point khác null. Hai phương thức dưới đây dùng hai record ở mục 1 và trả về kết quả tương đương.

**Trước — dùng type pattern rồi gọi accessor:**

~~~java
static String showOld(Object candidate) {
    if (!(candidate instanceof Segment segment)) {
        return "Không có đoạn thẳng đầy đủ";
    }

    Point start = segment.start();
    Point end = segment.end();
    if (start == null || end == null) {
        return "Không có đoạn thẳng đầy đủ";
    }

    return "(%d, %d) -> (%d, %d)".formatted(
            start.x(), start.y(), end.x(), end.y());
}
~~~

**Sau — dùng record pattern lồng nhau:**

~~~java
static String showNew(Object candidate) {
    if (candidate instanceof Segment(
            Point(int startX, int startY),
            Point(int endX, int endY))) {
        return "(%d, %d) -> (%d, %d)".formatted(
                startX, startY, endX, endY);
    }
    return "Không có đoạn thẳng đầy đủ";
}
~~~

Ở phiên bản sau, điều kiện thể hiện ngay một yêu cầu: **đầu vào là Segment và hai đầu của nó đều là Point**. Người đọc nhìn thấy bốn tọa độ được dùng mà không phải lần theo các biến start, end và bốn lần gọi accessor. Đây là cải thiện về độ rõ khi trọng tâm của nhánh là **cấu trúc dữ liệu**.

Lưu ý: nếu start hoặc end là null thì mẫu lồng Point(...) **không khớp**, do đó đi đến nhánh trả về thông báo không hợp lệ. Nếu nghiệp vụ cần phân biệt “không phải Segment” với “Segment thiếu điểm”, hãy viết nhánh xử lý riêng; không gộp hai tình huống chỉ để rút ngắn code.

## 3. Những tình huống record pattern làm code dễ hiểu hơn

| Tình huống | Vì sao sáng nghĩa hơn | Dấu hiệu nên dùng |
| --- | --- | --- |
| Kiểm tra kiểu và đọc nhiều thành phần | Điều kiện vừa xác nhận kiểu, vừa nêu các giá trị cần dùng | Một nhánh đọc x, y hoặc nhiều component |
| Dữ liệu lồng record | Bộc lộ hình dạng mà xử lý yêu cầu; giảm các biến trung gian | Segment chứa hai Point; Order chứa một record địa chỉ |
| Các nhánh xử lý phụ thuộc hình dạng dữ liệu | Mỗi nhánh của switch mô tả trường hợp áp dụng | Phân loại các record khác nhau từ Object hoặc kiểu cha |
| Điều kiện phụ đơn giản sau khi giải cấu trúc | Biến được đặt tên rõ ràng, điều kiện **when** diễn đạt quy tắc ngắn | Hai tọa độ bằng nhau, giá trị vượt ngưỡng |

Ví dụ: nhánh xử lý một đoạn thẳng có hai đầu trùng nhau có thể viết theo mẫu Segment(Point(...), Point(...)) kết hợp **when startX == endX && startY == endY**. Người đọc thấy ngay dữ liệu cần so sánh và điều kiện áp dụng, thay vì suy từ các chuỗi accessor.

Sự rõ ràng phụ thuộc vào **tên biến và độ sâu**: startX, startY, endX, endY hữu ích hơn a, b, c, d. Khi mẫu lồng quá nhiều cấp, nên tách thành bước xử lý hoặc phương thức có tên thể hiện nghiệp vụ.

## 4. Ví dụ Java 21 hoàn chỉnh: dùng switch để phân loại

Ví dụ sau kiểm tra cả mẫu lồng nhau, điều kiện **when**, giá trị null ở component và selector null. Đây là chương trình độc lập, có thể biên dịch và chạy:

~~~java
public class RecordPatternClarityDemo {
    record Point(int x, int y) {}
    record Segment(Point start, Point end) {}

    static String describe(Object value) {
        return switch (value) {
            case Segment(Point(int x1, int y1), Point(int x2, int y2))
                    when x1 == x2 && y1 == y2 ->
                    "Point: (%d, %d)".formatted(x1, y1);

            case Segment(Point(int x1, int y1), Point(int x2, int y2)) ->
                    "Segment: (%d, %d) -> (%d, %d)"
                            .formatted(x1, y1, x2, y2);

            case null -> "Null";
            default -> "Not a complete Segment";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(
                new Segment(new Point(1, 2), new Point(4, 6))));
        System.out.println(describe(
                new Segment(new Point(3, 3), new Point(3, 3))));
        System.out.println(describe(
                new Segment(new Point(1, 2), null)));
        System.out.println(describe(null));
    }
}
~~~

Lưu tệp với tên **RecordPatternClarityDemo.java** và chạy bằng JDK 21+:

~~~bash
javac RecordPatternClarityDemo.java
java RecordPatternClarityDemo
~~~

Đầu ra:

~~~text
Segment: (1, 2) -> (4, 6)
Point: (3, 3)
Not a complete Segment
Null
~~~

Giải thích thứ tự nhánh:

1. Nhánh có **when** đứng trước vì nó cụ thể hơn: chỉ khớp khi cả hai Point tồn tại và có cùng tọa độ.
2. Nhánh Segment không có điều kiện phụ xử lý các đoạn thẳng còn lại có hai Point hợp lệ. Nếu đặt nhánh tổng quát này trước, nhánh cùng mẫu có **when** ở sau sẽ bị che khuất và không biên dịch.
3. Segment có end = null không khớp với mẫu Point(...) lồng nhau, nên đi vào default.
4. Giá trị selector null được xử lý bởi **case null**. Với switch pattern matching, không nên trông chờ **default** tự xử lý selector null; thiếu nhánh null phù hợp có thể gây NullPointerException.

Trong **instanceof**, mẫu không khớp thì điều kiện là false. Biến được giới thiệu bởi pattern chỉ sử dụng được ở vùng mà trình biên dịch xác định pattern đã khớp. Trong **switch**, các biến pattern thuộc phạm vi nhánh tương ứng.

## 5. Khi nào giữ accessor hoặc type pattern sẽ rõ hơn?

**Chỉ cần một thành phần.** Nếu xử lý đơn giản là kiểm tra một Point và dùng duy nhất x, biểu thức sau thường đã trực tiếp, không cần giải cấu trúc cả y:

~~~java
if (candidate instanceof Point point && point.x() > 0) {
    System.out.println(point.x());
}
~~~

**Cần dùng chính đối tượng record.** Nếu nhiều lần truyền Point vào các phương thức khác hoặc gọi hành vi trên đối tượng, giữ biến point có thể tiện hơn việc chỉ lấy các thành phần.

**Điều kiện nghiệp vụ phức tạp.** Khi nhiều quy tắc, kiểm tra tính hợp lệ hoặc các quyết định không phụ thuộc trực tiếp vào hình dạng record, một phương thức như isEligible(order) diễn đạt mục đích rõ hơn mẫu lồng dài và nhiều điều kiện khiên cưỡng. Record pattern chỉ trích xuất dữ liệu; bản thân nó không thay thế kiểm tra nghiệp vụ.

**Cấu trúc lồng quá sâu.** Khi một dòng có nhiều record con và hàng loạt tên biến, cấu trúc chi tiết có thể che mục tiêu xử lý. Tách thành những bước có tên giúp bảo trì dễ hơn.

**Kiểu dữ liệu không phải record.** Record pattern áp dụng cho kiểu record. Với lớp Java thông thường, dùng type pattern (ví dụ instanceof Customer customer) và các phương thức phù hợp; không thể tùy ý dùng cú pháp Customer(...) để giải cấu trúc một class thường.

## 6. Lưu ý để không đánh đổi tính đúng đắn lấy sự ngắn gọn

- **Phiên bản:** dùng JDK 21+ để biên dịch record pattern thông thường. JDK 19 và 20 từng cung cấp tính năng ở dạng preview; JDK 17 không hỗ trợ record pattern.
- **Null:** selector null trong instanceof không khớp; component null có thể làm mẫu record lồng cụ thể không khớp. Thiết kế nhánh null và nhánh dữ liệu thiếu rõ ràng nếu nghiệp vụ cần phân biệt.
- **Thứ tự switch:** đặt các case có điều kiện **when** cụ thể trước case cùng kiểu tổng quát để tránh bị che khuất.
- **Phạm vi biến:** biến trích xuất được chỉ có hiệu lực nơi pattern chắc chắn đã khớp; đừng dùng chúng ở nhánh không khớp.
- **Tên có nghĩa:** ưu tiên những tên thể hiện vai trò (startX, endY, city) và xuống dòng tại ranh giới của các record lồng nhau.
- **Giữ nguyên ý nghĩa:** khi đổi từ accessor sang record pattern, kiểm tra lại hành vi với đầu vào sai kiểu, record chứa null, selector null và mọi đường đi của switch.

## 7. Tự quyết định có nên dùng hay không

Hãy tự hỏi: (1) dữ liệu đầu vào có phải record không; (2) nhánh này có cần nhiều component, hoặc cần nhìn ngay cấu trúc lồng nhau không; (3) mẫu sau khi đặt tên biến có ngắn, dễ đọc hơn các bước accessor không; (4) các trường hợp null và điều kiện nghiệp vụ có còn được xử lý đúng không?

Nếu những câu trả lời đó ủng hộ record pattern, hãy dùng để đưa **hình dạng dữ liệu** về đúng nơi quyết định xử lý. Nếu chỉ cần một accessor hoặc mẫu trở nên rối, một type pattern và phương thức có tên rõ ràng sẽ dễ hiểu hơn.