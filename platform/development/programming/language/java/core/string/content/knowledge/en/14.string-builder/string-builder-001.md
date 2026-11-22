# `StringBuilder`: Bộ đệm ký tự có thể thay đổi và mô hình xây dựng chuỗi

## 1. Tại sao cần `StringBuilder`?

Trong Java, `String` là **bất biến** (*immutable*): một đối tượng `String` đã được tạo không thể bị sửa nội dung qua API công khai. Các biểu thức như nối chuỗi, thay thế hoặc cắt chuỗi tạo ra giá trị chuỗi kết quả; biến có thể được gán tham chiếu khác nhưng nội dung đối tượng `String` cũ không đổi.

`StringBuilder` giải quyết nhu cầu khác: **xây dựng và chỉnh sửa dần một dãy ký tự trên cùng một đối tượng có thể thay đổi**. Nó đặc biệt hữu ích khi cần thêm nhiều phần vào kết quả, ghép dữ liệu trong vòng lặp, thay một đoạn văn bản, chèn vào giữa hoặc xóa ký tự.

~~~java
String text = "Hello";
text += " Java"; // text trỏ tới giá trị String mới

StringBuilder builder = new StringBuilder("Hello");
builder.append(" Java"); // cùng đối tượng builder được thay đổi
~~~

Cả hai có thể cho giá trị văn bản `"Hello Java"`. Khác biệt quan trọng là **mô hình đối tượng**: `String` giữ bất biến; `StringBuilder` có trạng thái có thể sửa, gồm dãy ký tự hiện tại và dung lượng bộ đệm đang cấp phát.

**Mục tiêu:** hiểu lúc nào nên dùng builder, cách `append` hoạt động, khác biệt `length`/`capacity`, các thao tác sửa tại chỗ, chuyển thành `String`, cách xử lý UTF-16 và giới hạn thread-safety.

## 2. Mô hình bộ đệm ký tự có thể thay đổi

Hãy xem một `StringBuilder` như một vùng chứa dãy **UTF-16 code unit** có hai đại lượng chính:

- **`length()`**: số code unit hiện đang thuộc **nội dung có hiệu lực** của builder.
- **`capacity()`**: số code unit bộ đệm có thể giữ **trước khi cần tăng dung lượng**. Luôn có `0 <= length() <= capacity()`.

Một mô hình trực quan:

~~~text
builder = new StringBuilder(8)
length = 0; capacity = 8

Sau append("Java"):
nội dung: [J][a][v][a][ ][ ][ ][ ]
          ^-----------^ ^---------^
             length=4     còn trống
capacity=8

Sau append(" 21"):
nội dung: [J][a][v][a][ ][2][1][ ]
length=7; capacity>=8

Sau append thêm cho vượt capacity:
builder tự mở rộng bộ đệm khi cần;
nội dung cũ được giữ nguyên.
~~~

Đó là **mô hình logic**, không phải cam kết `StringBuilder` luôn được lưu trong một `char[]` vật lý hay luôn tăng capacity theo một tỷ lệ cố định. Cách tổ chức byte/mảng, cấp phát, tối ưu và growth policy cụ thể có thể khác theo JDK.

**Vì sao tái sử dụng bộ đệm hữu ích?** Nếu phải nối lần lượt nhiều phần, builder có thể tái dùng chỗ đã cấp phát, thay vì buộc chương trình biểu diễn mỗi trạng thái trung gian thành một giá trị `String` mới. Điều này thường hữu ích cho quy trình ghép liên tục, dù `+` của Java hiện đại cũng có tối ưu riêng.

## 3. Bản đồ lựa chọn API khi xây dựng chuỗi

Thay vì ghi nhớ một danh sách lệnh, hãy bắt đầu từ **kiểu thay đổi cần thực hiện**. Những bài tiếp theo đi sâu vào tham số, điều kiện biên và ngoại lệ của từng nhóm.

| Mục tiêu | API thường dùng | Lưu ý quyết định |
| --- | --- | --- |
| Tạo builder rỗng hoặc có văn bản ban đầu | `new StringBuilder()`, `new StringBuilder(n)`, `new StringBuilder(text)` | Đối số `int` dự trù capacity; `String` cung cấp nội dung |
| Nối dần dữ liệu | `append(value)` | Overload được chọn theo kiểu biểu thức; trả chính builder |
| Nối một Unicode code point từ `int` | `appendCodePoint(cp)` | Code point ngoài BMP chiếm hai code unit; `append(cp)` lại nối chữ số |
| Chỉnh nội dung theo vị trí | `insert`, `delete`, `deleteCharAt`, `replace` | Chỉ số theo UTF-16; `[start,end)` thường loại trừ biên cuối |
| Đổi một đơn vị ký tự hoặc độ dài logic | `setCharAt(i,ch)`, `setLength(n)` | Hai phương thức trả `void`; tăng length bổ sung NUL |
| Dự trù hoặc thử thu gọn vùng đệm | `ensureCapacity(n)`, `trimToSize()` | Không thay đổi nội dung; `trimToSize` là yêu cầu best-effort |
| Đảo hoặc nối lặp dữ liệu | `reverse()`, `repeat(...)` | Đảo không bảo toàn mọi grapheme cluster; `repeat` của builder cần Java 21+ |
| Lấy kết quả ổn định | `toString()` | Trả `String` có nội dung không đổi khi builder tiếp tục sửa |

Một ví dụ ngắn cho thấy **việc chọn API dựa trên mục tiêu**:

~~~java
StringBuilder line = new StringBuilder("id=");
line.append(42);            // thêm số thành văn bản: "id=42"
line.insert(0, "[");        // chèn dấu mở
line.append(']');           // nối dấu đóng
String finished = line.toString(); // "[id=42]"
~~~

Mỗi lệnh nhìn thấy trạng thái sau lệnh trước. Nếu giữ `finished` rồi tiếp tục sửa `line`, `finished` vẫn mang nội dung ban đầu. Bởi vậy, một builder thích hợp để **lắp ráp**, còn `String` thích hợp làm **kết quả đã chốt**.

## 4. Chương trình hoàn chỉnh Java 17+: quan sát mô hình xây dựng chuỗi

Tạo tệp **`StringBuilderModelDemo.java`**:

~~~java
public class StringBuilderModelDemo {
    public static void main(String[] args) {
        StringBuilder sb = new StringBuilder(4);
        System.out.println("initial=" + sb.length() + "/" + sb.capacity());

        sb.append("Java").append(' ').append(21);
        System.out.println("built=" + sb);
        System.out.println("length=" + sb.length());
        System.out.println("capacityEnough=" + (sb.capacity() >= sb.length()));

        String snapshot = sb.toString();
        sb.insert(5, "SE ");
        System.out.println("insert=" + sb);

        sb.replace(5, 7, "Core");
        System.out.println("replace=" + sb);

        sb.delete(9, 12);
        sb.setCharAt(0, 'j');
        System.out.println("edited=" + sb);
        System.out.println("snapshot=" + snapshot);

        sb.setLength(4);
        System.out.println("shortened=" + sb);
        sb.setLength(6);
        System.out.println("paddedCodeUnits="
                + (int) sb.charAt(4) + "," + (int) sb.charAt(5));

        StringBuilder unicode = new StringBuilder()
                .append('A')
                .appendCodePoint(0x1F600)
                .append('B');
        System.out.println("unicodeLength=" + unicode.length());
        System.out.println("unicodeCodePoints="
                + unicode.codePointCount(0, unicode.length()));

        StringBuilder comparison = new StringBuilder("java");
        System.out.println("sameText=" + sb.substring(0, 4)
                .contentEquals(comparison));
        System.out.println("sameBuilderContent="
                + new StringBuilder("java").toString()
                        .equals(comparison.toString()));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 -encoding UTF-8 StringBuilderModelDemo.java
java StringBuilderModelDemo
~~~

`stdout` đã xác nhận qua biên dịch/chạy:

~~~text
initial=0/4
built=Java 21
length=7
capacityEnough=true
insert=Java SE 21
replace=Java Core 21
edited=java Core
snapshot=Java 21
shortened=java
paddedCodeUnits=0,0
unicodeLength=4
unicodeCodePoints=3
sameText=true
sameBuilderContent=true
~~~

Giải thích kết quả:

1. Constructor yêu cầu capacity `4` nhưng nội dung ban đầu rỗng, nên `initial=0/4`.
2. `append` nối lần lượt `"Java"`, dấu cách và số `21`, tạo văn bản `"Java 21"` dài 7 code unit. Builder mở rộng nếu cần; ví dụ chỉ kiểm tra invariant `capacity >= length`.
3. `insert` chèn `"SE "` trước số `21`. `replace` thay `"SE"` bằng `"Core"`. `delete` bỏ phần `" 21"` và `setCharAt` đổi `J` thành `j`.
4. Biến `snapshot` là `String` lấy **trước** các sửa đổi, nên vẫn là `"Java 21"` trong khi builder thành `"java Core"`.
5. `setLength(4)` cắt dãy còn `"java"`; `setLength(6)` bổ sung hai code unit `U+0000` có giá trị số `0`.
6. `appendCodePoint(0x1F600)` thêm một emoji bằng **hai UTF-16 code unit**. Cùng với `A` và `B`, `unicode.length() == 4` nhưng có 3 code point.
7. `substring(0, 4)` lấy chuỗi `"java"`, và `String.contentEquals(CharSequence)` cho phép so với nội dung của builder. Kết quả so hai `String` tạo từ builder cũng là `true`.

## 5. Cách suy luận đúng từ mô hình mutable

**Một builder là một đối tượng có trạng thái.** Ví dụ `StringBuilder alias = builder;` chỉ tạo tham chiếu thứ hai tới cùng đối tượng; `alias.append(...)` sẽ làm thay đổi văn bản mà `builder` nhìn thấy. Khi cần kết quả ổn định để truyền giữa các thành phần, lấy một `String` qua `toString()`, thay vì đưa builder mutable cho bên khác tự sửa.

**Giới hạn chỉ số đến từ `length()`, không phải `capacity()`.** Một vùng đệm còn dư chỗ chưa làm cho `charAt(length())` hợp lệ. Với emoji bổ sung như 😀, `length()` tăng hai đơn vị UTF-16, còn số code point tăng một. Các thao tác sửa theo vị trí có thể cắt đôi surrogate pair; nếu cần xử lý theo ký tự hiển thị, phải xét cả grapheme cluster.

**Chọn công cụ theo vòng đời dữ liệu.** Một phép nối `String` bằng `+` ngắn thường rõ ràng và có thể được Java tối ưu. Khi gom nhiều mẩu trong một vòng lặp, dùng builder cục bộ thường phù hợp; chỉ dự trù capacity khi có ước lượng đáng tin và nhu cầu hiệu năng thực tế. `StringBuilder` không có đồng bộ nội bộ để dùng chung an toàn giữa những luồng cùng sửa; ưu tiên một nơi sở hữu builder hoặc phối hợp truy cập bằng cơ chế đồng bộ rõ ràng.

## 6. Câu hỏi tự kiểm tra

**Câu 1.** `new StringBuilder(32).length()` bằng bao nhiêu, và `capacity()` bằng bao nhiêu?

**Đáp án:** length bằng `0`, capacity bằng `32`. Không có ký tự nào được thêm chỉ vì đã dành chỗ.

**Câu 2.** Hai lệnh `builder.append("a"); builder.append("b");` có tạo ra hai builder mới không?

**Đáp án:** không. Cả hai sửa cùng đối tượng builder và nội dung tích lũy thành `"ab"`.

**Câu 3.** Sau `String saved = builder.toString(); builder.append("!");`, nội dung `saved` có đổi không?

**Đáp án:** không. `saved` là `String` bất biến chứa trạng thái lúc `toString` được gọi.

**Câu 4.** `ensureCapacity(200)` và `setLength(200)` khác nhau thế nào?

**Đáp án:** `ensureCapacity` dự trù tối thiểu 200 code unit mà không đổi nội dung; `setLength` làm độ dài nội dung bằng 200, cắt bớt hoặc thêm `\u0000` tùy trạng thái hiện tại.

**Câu 5.** Vì sao `new StringBuilder("😀").length()` bằng `2`?

**Đáp án:** emoji `U+1F600` cần một cặp surrogate gồm hai code unit UTF-16; `length` đếm code unit.

**Câu 6.** Có an toàn khi hai luồng đồng thời gọi `append` lên một `StringBuilder` chung không?

**Đáp án:** không có bảo đảm thread-safe nếu không đồng bộ; ưu tiên builder cục bộ hoặc cơ chế phối hợp thích hợp.

**Câu 7.** `StringBuilder("x").equals(new StringBuilder("x"))` có trả true vì cùng chữ `x` không?

**Đáp án:** không. `StringBuilder` không so nội dung bằng `equals`; hai instance khác nhau không bằng theo identity. Dùng `toString().equals(...)` để so văn bản.

**Câu 8.** Vì sao không nên gọi `trimToSize()` sau mọi lần nối trong vòng lặp?

**Đáp án:** builder có thể phải mở rộng lại ngay sau đó; hành vi này có thể tăng chi phí cấp phát và sao chép thay vì tận dụng capacity dư.

## 7. Tài liệu chuẩn

- [Java SE 17 — `StringBuilder`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StringBuilder.html): constructor, `append`, `insert`, `delete`, `replace`, `toString` và hợp đồng thread-safety.
- [Java SE 17 — `AbstractStringBuilder`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AbstractStringBuilder.html): `length`, `capacity`, `ensureCapacity`, `setLength` và thao tác code unit.
- [Java SE 17 — `String`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): tính bất biến, chuỗi giá trị và phép so `equals`.
- [Java SE 17 — `StringBuffer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StringBuffer.html): bộ đệm có đồng bộ và giới hạn thao tác ghép nhiều bước.

**Ghi nhớ:** `StringBuilder` là một **đối tượng mutable tích lũy văn bản trong bộ đệm có thể mở rộng**. `length` là số code unit hiện có; `capacity` là dung lượng dự trù. Các thao tác `append/insert/delete/replace` sửa cùng builder; `toString` trả giá trị `String` bất biến; builder không tự đồng bộ giữa nhiều luồng.
