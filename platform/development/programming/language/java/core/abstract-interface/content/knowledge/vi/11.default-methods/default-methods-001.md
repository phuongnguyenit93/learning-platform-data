# Vì sao Java bổ sung default method?

Trước Java 8, một interface chủ yếu mô tả những phương thức mà lớp triển khai phải cung cấp. Khi thư viện muốn bổ sung một thao tác vào interface công khai đã được nhiều dự án triển khai, thêm phương thức abstract mới thường buộc các lớp cụ thể phải được sửa và biên dịch lại. Với một API phổ biến, số lượng implementer có thể lớn hơn nhiều so với khả năng kiểm soát của tác giả thư viện.

## 1. Bài toán tiến hóa API

Giả sử phiên bản đầu của thư viện có hợp đồng:

```java
interface ReportExporter {
    String export(String content);
}
```

Các lớp như `CsvExporter` chỉ biết cài đặt `export`. Nếu phiên bản tiếp theo thêm `String exportNormalized(String content);` dưới dạng abstract, lớp cũ sẽ thiếu implementation khi biên dịch lại.

Java 8 bổ sung **default method** để interface có thể cung cấp một hành vi mặc định dùng được ngay:

```java
interface ReportExporter {
    String export(String content);

    default String exportNormalized(String content) {
        return export(content.trim());
    }
}

final class CsvExporter implements ReportExporter {
    @Override
    public String export(String content) {
        return "CSV:" + content;
    }
}
```

`CsvExporter` không cần viết lại `exportNormalized`. Default method chuẩn hóa nội dung rồi gọi phương thức abstract `export`; lời gọi sau được phân phối tới implementation của đối tượng thực tế. Lớp vẫn có thể override nếu quy tắc chuẩn hóa của nó khác.

## 2. Lợi ích với API chuẩn của Java

Tính năng này đặc biệt hữu ích khi Java 8 bổ sung lambda, method reference và Stream API. Các interface được triển khai rộng rãi có thể nhận thao tác mới mà không buộc mọi nhà cung cấp phải chép cùng một logic.

| Interface | Ví dụ default method | Tác dụng |
| --- | --- | --- |
| `Iterable` | `forEach(Consumer)` | Duyệt bằng lambda hoặc method reference. |
| `Collection` | `stream()`, `parallelStream()`, `removeIf(Predicate)` | Xây dựng pipeline và thao tác theo điều kiện. |
| `List` | `replaceAll(UnaryOperator)`, `sort(Comparator)` | Biến đổi hoặc sắp xếp phần tử. |
| `Map` | `getOrDefault`, `forEach`, `computeIfAbsent` | Thao tác tiện ích trên ánh xạ. |

Một implementation chuyên biệt vẫn có thể override để đáp ứng cấu trúc dữ liệu, hiệu năng hoặc cam kết riêng của nó. Default method không bảo đảm thuật toán tổng quát là tối ưu cho mọi lớp.

## 3. Ba loại tương thích cần phân biệt

- **Tương thích mã nguồn:** khi lớp cũ được biên dịch lại, default method thường giúp lớp tiếp tục đáp ứng interface mà không cần thêm phương thức mới.
- **Tương thích nhị phân:** các chương trình đã biên dịch có thể tiếp tục liên kết trong nhiều trường hợp vì JVM có thể chọn implementation mặc định khi được gọi.
- **Tương thích hành vi:** hành vi mới vẫn phải có ý nghĩa với mọi implementation hợp lệ. Một default method dựa vào giả định sai về dữ liệu hoặc trạng thái có thể gây lỗi nghiệp vụ dù chương trình vẫn biên dịch.

Đây là hỗ trợ tương thích, không phải bảo đảm tuyệt đối. Một default method mới có thể va chạm với phương thức đã tồn tại trong class hoặc interface khác. Khi có nhiều default method cạnh tranh, cần xét quy tắc kế thừa và có thể phải override để giải quyết.

## 4. Khi nào nên thêm default method?

Hãy cân nhắc khi hành vi mới có thể được xây dựng từ các thao tác đã nằm trong hợp đồng và mặc định đó hợp lý với mọi implementation. Nếu mỗi lớp phải làm một việc khác nhau, một phương thức abstract có thể diễn đạt yêu cầu rõ hơn. Nếu thuật toán cần trạng thái instance, constructor hoặc một giao dịch atomic, nên cân nhắc lớp cơ sở hay đối tượng thành phần.

Trước khi phát hành API, kiểm tra các implementer tiêu biểu, chữ ký có thể xung đột, tiền điều kiện, ngoại lệ, side effect và đặc tính đồng thời. Mục tiêu là thêm một hành vi dùng chung an toàn, chứ không chỉ làm cho mã nguồn ngắn hơn.

## Tự kiểm tra

1. Vì sao thêm phương thức abstract vào interface phổ biến có thể làm lớp triển khai cũ không biên dịch lại được?
2. Default method giảm gánh nặng đó bằng cách nào?
3. Vì sao một default method mới vẫn có thể gây lỗi tương thích?
4. Khi nào phương thức abstract hoặc một service phù hợp hơn một default method?

**Ghi nhớ:** default method giúp interface tiến hóa cùng API mới trong khi nhiều lớp hiện hữu vẫn có thể dùng hành vi chung. Tính tương thích vẫn phụ thuộc vào quy tắc kế thừa và tính đúng đắn của hợp đồng.