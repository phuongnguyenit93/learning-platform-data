# StringBuilder.toString(): kết quả độc lập với những thay đổi về sau

## 1. Ý nghĩa của “độc lập”

`StringBuilder` là đối tượng **có thể thay đổi** (mutable): sau khi tạo, ta có thể `append`, `insert`, `delete`, `replace`, `setCharAt`, `reverse` hoặc `setLength` để sửa dãy ký tự đang giữ. Ngược lại, `String` là **bất biến** (immutable): nội dung của một chuỗi `String` đã tạo không thể bị sửa tại chỗ.

Khi gọi `String snapshot = builder.toString();`, phương thức lấy **nội dung của `builder` tại thời điểm gọi** và trả về một `String` có nội dung đó. Theo hợp đồng API của `StringBuilder.toString()`, các thay đổi tiếp theo đối với `StringBuilder` **không ảnh hưởng** đến nội dung `String` vừa trả về.

- `snapshot` là giá trị văn bản đã chốt tại thời điểm gọi, không phải “cửa sổ” theo dõi `builder`.
- `builder` vẫn tồn tại và tiếp tục sửa được; `toString()` không khóa, xóa hay đặt lại nó.
- Muốn lấy trạng thái mới, phải gọi `builder.toString()` một lần nữa và giữ kết quả mới.

## 2. Ví dụ Java 17+ chạy độc lập

Lưu chương trình sau thành `StringBuilderSnapshotDemo.java`:

```java
public class StringBuilderSnapshotDemo {
    public static void main(String[] args) {
        StringBuilder builder = new StringBuilder("Java");

        String first = builder.toString();      // Chụp "Java"
        builder.append(" 17");

        String second = builder.toString();     // Chụp "Java 17"
        builder.replace(0, 4, "OpenJDK");       // Sửa chính builder

        System.out.println("first   = " + first);
        System.out.println("second  = " + second);
        System.out.println("builder = " + builder);
        System.out.println("second still matches builder? "
                + second.contentEquals(builder));
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```bash
javac StringBuilderSnapshotDemo.java
java StringBuilderSnapshotDemo
```

Kết quả chuẩn:

```text
first   = Java
second  = Java 17
builder = OpenJDK 17
second still matches builder? false
```

Diễn biến của ba giá trị:

| Thời điểm | Nội dung `builder` | `first` | `second` |
| --- | --- | --- | --- |
| Ngay sau `first = builder.toString()` | `Java` | `Java` | Chưa tạo |
| Sau `append(" 17")` và lần gọi `toString()` thứ hai | `Java 17` | `Java` | `Java 17` |
| Sau `replace(0, 4, "OpenJDK")` | `OpenJDK 17` | `Java` | `Java 17` |

`replace(0, 4, ...)` thay các ký tự ở vị trí từ `0` đến trước `4` trong **builder hiện tại**. Hai biến kiểu `String` vẫn giữ đúng nội dung lúc được tạo. Phép kiểm tra `contentEquals` cuối cùng trả về `false` vì `Java 17` khác `OpenJDK 17`.

## 3. Phân biệt bản chụp với tham chiếu đến StringBuilder

Một biến khác trỏ vào cùng `StringBuilder` sẽ quan sát những lần sửa tiếp theo của đối tượng đó. Ví dụ đoạn mã sau đặt **bên trong `main`**:

```java
StringBuilder builder = new StringBuilder("A");
StringBuilder alias = builder;
CharSequence sequence = builder;
String snapshot = builder.toString();

builder.append("B");

System.out.println(alias);     // AB
System.out.println(sequence);  // AB
System.out.println(snapshot);  // A
```

- `alias` và `sequence` cùng tham chiếu đến `builder`, nên khi in ra sau `append`, chúng biểu diễn nội dung mới `AB`.
- `snapshot` là `String` được tạo **trước** khi `append`, nên vẫn là `A`.
- Kiểu khai báo `CharSequence` tự nó **không bảo đảm bất biến**: đối tượng thực tế có thể là `StringBuilder` mutable hoặc `String` immutable.

Điều này cũng giải thích vì sao `System.out.println(builder)` in trạng thái của builder lúc lệnh chạy; nó không lưu một bản chụp để các lệnh in tương lai tự tái sử dụng.

## 4. Vì sao Java bảo đảm được điều đó?

`StringBuilder` quản lý một dãy ký tự có thể sửa. `toString()` tạo kết quả kiểu `String` biểu diễn dãy ký tự **tại lần gọi đó**. Từ bên ngoài, kết quả tuân theo tính bất biến của `String` và không chia sẻ trạng thái *có thể bị chỉnh sửa trực tiếp* với `StringBuilder` theo cách khiến nội dung chuỗi cũ biến đổi.

Đây là **bảo đảm về hành vi của API**, không phụ thuộc vào việc phiên bản JVM lưu ký tự bằng mảng byte, mã hóa nội bộ nào hay tối ưu bộ nhớ ra sao. Không cần dựa vào chi tiết triển khai để tin vào tính độc lập về **nội dung** giữa bản chụp và các sửa đổi về sau.

Cần phân biệt rõ hai chiều: sửa `builder` không làm thay đổi `snapshot`; ngược lại, `snapshot` cũng không tạo ra khả năng chỉnh sửa `builder`. `String` không có các thao tác sửa ký tự tại chỗ như `setCharAt`.

## 5. Khi nào nên gọi toString(), và những lỗi thường gặp

**Khi cần giá trị ổn định:** gọi `toString()` sau khi đã tạo được nội dung mong muốn, ví dụ trước khi trả kết quả từ một phương thức, lưu thông điệp để xử lý về sau hoặc truyền dữ liệu đến API nhận `String`.

**Khi còn xây dựng nội dung:** tiếp tục dùng `StringBuilder` để nối/sửa. Việc gọi `toString()` trong mỗi vòng lặp chỉ để quan sát giá trị trung gian có thể tạo nhiều chuỗi và phát sinh chi phí thời gian/bộ nhớ theo độ dài văn bản. Chỉ tạo bản chụp ở những mốc thật sự cần.

Những nhầm lẫn cần tránh:

1. **Nghĩ rằng bản chụp tự cập nhật.** `String old = builder.toString(); builder.append("!");` không sửa `old`. Gọi `toString()` lần nữa nếu muốn chuỗi mới.
2. **Nghĩ rằng `toString()` làm builder bất biến hoặc rỗng.** Phương thức này chỉ trả về `String`; không thay đổi nội dung builder.
3. **Giữ một alias rồi tưởng đó là bản chụp.** `StringBuilder other = builder;` chỉ tạo thêm tham chiếu đến cùng đối tượng. Dùng `String other = builder.toString();` để lấy giá trị ổn định.
4. **Dùng `==` để so nội dung hai `String`.** `==` kiểm tra cùng tham chiếu hay không; hãy dùng `equals` hoặc `contentEquals` khi cần kiểm tra nội dung.
5. **Suy ra rằng `StringBuilder` an toàn khi nhiều luồng cùng sửa.** `StringBuilder` không được đồng bộ hóa; nếu có truy cập đồng thời, phải phối hợp truy cập để bản chụp được lấy ở trạng thái nhất quán. Tính bất biến của `String` đã trả về không tự xử lý tranh chấp khi đang đọc builder.

## 6. Tự kiểm tra

Dự đoán kết quả đoạn mã sau, rồi có thể đặt nó vào `main` để chạy:

```java
StringBuilder b = new StringBuilder("AB");
String x = b.toString();

b.setCharAt(0, 'Z');
String y = b.toString();

b.deleteCharAt(1);
System.out.println(x + " | " + y + " | " + b);
```

Kết quả:

```text
AB | ZB | Z
```

`x` giữ `AB`; `y` giữ `ZB`; `b` còn `Z` sau khi xóa ký tự ở vị trí `1`. Mỗi lần gọi `toString()` đánh dấu **một bản chụp nội dung riêng tại thời điểm đó**.