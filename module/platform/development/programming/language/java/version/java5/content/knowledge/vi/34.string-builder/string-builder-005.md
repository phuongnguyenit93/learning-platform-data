# length(), capacity() và ensureCapacity() trong StringBuilder

## 1. Phân biệt phần đã dùng với phần đã dành sẵn

StringBuilder giữ một dãy ký tự có thể thay đổi. Khi nối thêm dữ liệu, nó cần có chỗ chứa dãy đó. Hai con số mô tả hai khía cạnh khác nhau:

- `length()`: số đơn vị ký tự đang thuộc nội dung.
- `capacity()`: sức chứa hiện tại, bao gồm cả phần đã dùng và phần còn dự phòng.

Ví dụ dãy đang chứa `ABC` và có capacity 8:

```text
Nội dung hợp lệ:  A B C
length:          3
capacity:        8
Còn dự phòng:    5 đơn vị
```

Phần dự phòng không phải năm dấu cách hay năm ký tự NUL trong nội dung. `toString()` chỉ tạo kết quả từ nội dung hiện có. Chỉ số hợp lệ để đọc bằng `charAt()` vẫn dựa trên length, không dựa trên capacity.

Ở trạng thái sử dụng bình thường:

```text
0 <= length() <= capacity()
```

Nếu dữ liệu mới vượt sức chứa, builder có thể tăng bộ đệm. Capacity không phải giới hạn tối đa do nghiệp vụ đặt ra.

## 2. Vai trò của ba phương thức

| Phương thức | Trả về | Có thay nội dung không? | Công dụng |
| --- | --- | --- | --- |
| `length()` | int | Không | Biết độ dài nội dung đang có |
| `capacity()` | int | Không | Quan sát sức chứa hiện tại |
| `ensureCapacity(minimum)` | void | Không | Dành đủ sức chứa tối thiểu cho kế hoạch xây dựng tiếp |

`ensureCapacity()` không phải thao tác append, không đặt length bằng đối số và không tạo ra ký tự mới. Nó cũng không trả về builder để nối chuỗi phương thức.

Đoạn minh họa:

```java
StringBuilder builder = new StringBuilder(20);
builder.append("ABC");

int contentLength = builder.length(); // 3
int currentCapacity = builder.capacity(); // 20
builder.ensureCapacity(100); // Nội dung vẫn là ABC.
```

Các hợp đồng tương ứng có trong [StringBuilder API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/StringBuilder.html#ensureCapacity(int)).

## 3. ensureCapacity() nhận tổng sức chứa cần có

Đối số là **mức tổng tối thiểu**, không phải lượng cần cộng thêm vào capacity hay length.

Giả sử builder đã có nội dung dài 30 và sắp nối thêm 20 đơn vị. Nếu muốn dành chỗ cho kết quả, mức cần bảo đảm là 50:

```java
builder.ensureCapacity(50);
```

Gọi `ensureCapacity(20)` không có nghĩa “hãy đặt thêm chỗ cho 20 đơn vị”. Nếu sức chứa hiện tại đã lớn hơn 20, lời gọi đó không thay đổi gì.

Tương tự, `ensureCapacity(builder.capacity() + 20)` thường dành nhiều hơn nhu cầu thực khi builder đang có nhiều phần dự phòng. Cơ sở để dự tính kết quả thường là `length() + additionalLength`.

## 4. Khi nào sức chứa tăng?

Nếu capacity hiện tại đã đáp ứng yêu cầu, ensureCapacity không cần tăng. Nếu chưa đủ, với các kích thước thông thường mà phép cấp phát thực hiện được, API mô tả sức chứa mới theo mức lớn hơn giữa:

```text
minimumCapacity
và
2 × oldCapacity + 2
```

Ví dụ:

| Capacity cũ | Yêu cầu tối thiểu | Kết quả theo quy tắc tăng |
| --- | --- | --- |
| 4 | 3 | 4, đã đủ |
| 4 | 5 | 10 |
| 10 | 100 | 100 |
| 100 | 50 | 100, không thu nhỏ |

Vì vậy, sau `ensureCapacity(5)`, capacity có thể lớn hơn 5. Điều cần dùng trong thiết kế là “ít nhất đủ mức yêu cầu”, không phải “luôn bằng đúng đối số”.

Đối số bằng 0 hoặc âm khiến ensureCapacity không làm gì và trả về. Đây khác với constructor `new StringBuilder(-1)`, vốn báo `NegativeArraySizeException`. Đừng dùng việc ensureCapacity chấp nhận đối số âm như bằng chứng công thức tính dung lượng của ứng dụng là đúng.

### Chương trình hoàn chỉnh

Lưu thành `BuilderEnsureCapacityDemo.java`:

```java
public class BuilderEnsureCapacityDemo {
    private static void show(String label, StringBuilder builder) {
        System.out.println(label + ": text=[" + builder
                + "], length=" + builder.length()
                + ", capacity=" + builder.capacity());
    }

    public static void main(String[] args) {
        StringBuilder builder = new StringBuilder(4);
        builder.append("AB");
        show("initial", builder);

        builder.ensureCapacity(3);
        show("request 3", builder);

        builder.ensureCapacity(5);
        show("request 5", builder);

        builder.ensureCapacity(100);
        show("request 100", builder);

        builder.ensureCapacity(50);
        builder.ensureCapacity(0);
        builder.ensureCapacity(-1);
        show("smaller or nonpositive requests", builder);

        builder.setLength(0);
        show("cleared", builder);
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```shell
javac -encoding UTF-8 BuilderEnsureCapacityDemo.java
java BuilderEnsureCapacityDemo
```

Stdout chính xác:

```text
initial: text=[AB], length=2, capacity=4
request 3: text=[AB], length=2, capacity=4
request 5: text=[AB], length=2, capacity=10
request 100: text=[AB], length=2, capacity=100
smaller or nonpositive requests: text=[AB], length=2, capacity=100
cleared: text=[], length=0, capacity=100
```

Mọi lần ensureCapacity đều giữ nội dung `AB` và length bằng 2. Xóa nội dung bằng `setLength(0)` làm builder rỗng, nhưng phần dự trữ trong ví dụ vẫn còn.

## 5. Dành chỗ cho phần sắp thêm và phát hiện tràn số

Có thể đóng gói phép tính tổng độ dài cần thiết vào một hàm. Phải phân biệt ba lỗi:

1. Số lượng dự kiến thêm là âm: dữ liệu cấu hình sai.
2. Tổng length và phần thêm vượt phạm vi int: tràn số.
3. Tổng vẫn biểu diễn được bằng int nhưng JVM không đủ bộ nhớ để cấp phát: vấn đề tài nguyên.

Không nên viết phép cộng int rồi để tràn thành số âm; ensureCapacity có thể bỏ qua đối số âm, làm lỗi tính toán bị che khuất.

Lưu thành `ReserveAdditionalDemo.java`:

```java
public class ReserveAdditionalDemo {
    private static void reserveAdditional(StringBuilder builder,
                                          int additionalLength) {
        if (additionalLength < 0) {
            throw new IllegalArgumentException("Negative additional length");
        }

        int minimum = Math.addExact(builder.length(), additionalLength);
        builder.ensureCapacity(minimum);
    }

    public static void main(String[] args) {
        StringBuilder builder = new StringBuilder(4).append("ABCD");

        builder.ensureCapacity(3);
        System.out.println("after ensureCapacity(3) = "
                + builder.capacity());

        reserveAdditional(builder, 3);
        System.out.println("after reserving 3 more = "
                + builder.capacity());
        System.out.println("length before append = " + builder.length());

        builder.append("XYZ");
        System.out.println("result = " + builder);
        System.out.println("length after append = " + builder.length());
        System.out.println("capacity after append = " + builder.capacity());

        try {
            reserveAdditional(builder, Integer.MAX_VALUE);
        } catch (ArithmeticException ex) {
            System.out.println("overflow detected before allocation");
        }
    }
}
```

Chạy:

```shell
javac -encoding UTF-8 ReserveAdditionalDemo.java
java ReserveAdditionalDemo
```

Stdout chính xác:

```text
after ensureCapacity(3) = 4
after reserving 3 more = 10
length before append = 4
result = ABCDXYZ
length after append = 7
capacity after append = 10
overflow detected before allocation
```

Trước khi nối `XYZ`, builder dài 4; muốn thêm 3 thì mức tổng tối thiểu là 7. Capacity cũ bằng 4 nên quy tắc tăng cho 10. Lệnh dành chỗ chưa thay length; chỉ append mới làm length thành 7.

[Math.addExact](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Math.html#addExact(int,int)) ném ArithmeticException nếu kết quả cộng int bị tràn. Hàm minh họa không cố cấp phát dung lượng cực lớn để thử thiếu bộ nhớ.

Ngay cả khi phép cộng không tràn, không nên coi mọi giá trị int dương là dung lượng có thể cấp phát. Ứng dụng vẫn cần giới hạn kích thước đầu ra phù hợp.

## 6. Length và capacity dùng đơn vị UTF-16

Chữ “ký tự” trong cách đếm của các phương thức này cần được hiểu theo đơn vị char của Java, tức đơn vị mã UTF-16. Nó không phải số byte UTF-8 và không nhất thiết là số ký tự hiển thị.

Lưu thành `BuilderUnicodeLengthDemo.java`:

```java
public class BuilderUnicodeLengthDemo {
    public static void main(String[] args) {
        StringBuilder builder = new StringBuilder(8);
        builder.append('A');
        builder.appendCodePoint(0x1F600);
        builder.append('B');

        String before = builder.toString();

        System.out.println("UTF-16 length = " + builder.length());
        System.out.println("code point count = "
                + builder.codePointCount(0, builder.length()));
        System.out.println("initial capacity = " + builder.capacity());

        builder.ensureCapacity(12);

        System.out.println("content preserved = "
                + before.equals(builder.toString()));
        System.out.println("length after reserve = " + builder.length());
        System.out.println("capacity meets 12 = "
                + (builder.capacity() >= 12));
    }
}
```

Chạy:

```shell
javac -encoding UTF-8 BuilderUnicodeLengthDemo.java
java BuilderUnicodeLengthDemo
```

Stdout chính xác:

```text
UTF-16 length = 4
code point count = 3
initial capacity = 8
content preserved = true
length after reserve = 4
capacity meets 12 = true
```

Điểm mã `U+1F600` cần hai char UTF-16. Cộng với A và B, length là 4 nhưng số điểm mã là 3. Khi cộng độ dài các String để dự trữ, `String.length()` tương thích với đơn vị của builder.

Nếu cần giới hạn theo số điểm mã hoặc ký tự người dùng nhìn thấy, phải xây dựng quy tắc riêng; không dùng capacity để kiểm tra số ký tự hiển thị.

Capacity cũng không phải số byte bộ nhớ. Không dựa vào mô hình cố định “một capacity luôn chiếm đúng hai byte” để tính RAM; cách lưu trữ nội bộ thuộc triển khai.

## 7. ensureCapacity không thay thế setLength hoặc trimToSize

| Nhu cầu | Thao tác phù hợp | Điểm cần lưu ý |
| --- | --- | --- |
| Biết nội dung đang dài bao nhiêu | `length()` | Không bao gồm phần dự trữ |
| Chuẩn bị cho kết quả lớn hơn | `ensureCapacity(n)` | Không thêm ký tự |
| Cắt ngắn hoặc tăng độ dài nội dung | `setLength(n)` | Khi tăng, phần mới chứa NUL |
| Xóa nội dung để dùng tiếp | `setLength(0)` | Có thể giữ sức chứa lớn |
| Đề nghị giảm bộ nhớ dư | `trimToSize()` | Không có nghĩa luôn thu đúng bằng length |

Đoạn minh họa sự khác nhau:

```java
StringBuilder builder = new StringBuilder(20);

builder.ensureCapacity(50);
System.out.println(builder.length()); // 0

builder.setLength(3);
System.out.println(builder.length()); // 3
System.out.println((int) builder.charAt(0)); // 0: ký tự NUL
```

Ở đây setLength thật sự tạo phần nội dung dài 3. Không dùng nó để “đặt chỗ” trước append nếu không muốn các NUL đứng trước dữ liệu được thêm.

API mô tả trimToSize là một nỗ lực giảm phần lưu trữ dư và không bắt buộc phải làm capacity bằng length. Ngoài ra, các thao tác về sau có thể thay đổi sức chứa; ensureCapacity không phải một mức tối thiểu được khóa vĩnh viễn.

Nếu liên tục thu nhỏ rồi lại append dữ liệu lớn, lợi ích giữ bộ đệm để dùng lại bị mất và có thể phát sinh thêm thao tác cấp phát.

## 8. Khi nào dự trữ trước có giá trị?

Dự trữ trước có thể giảm số lần tăng bộ đệm và sao chép nội dung đang có. Nó hữu ích khi cấu trúc đầu ra cho phép ước lượng đáng tin, chẳng hạn độ dài các thành phần cộng với dấu phân cách.

Đoạn minh họa khi đã có các String không null:

```java
int expected = Math.addExact(header.length(), body.length());
expected = Math.addExact(expected, footer.length());

StringBuilder builder = new StringBuilder();
builder.ensureCapacity(expected);
builder.append(header).append(body).append(footer);
```

Nếu biết ước lượng ngay lúc tạo, `new StringBuilder(expected)` cũng diễn đạt đúng nhu cầu. ensureCapacity phù hợp khi builder đã tồn tại hoặc kế hoạch về kích thước được biết sau.

Tuy nhiên:

- Không cần dự trữ chính xác cho mọi phép nối ngắn.
- Ước lượng quá lớn giữ nhiều phần dư hơn cần thiết.
- Gọi ensureCapacity trước mọi lần append không tự động nhanh hơn.
- Có đủ capacity không phải cam kết toàn bộ thuật toán không cấp phát thêm đối tượng; chẳng hạn thao tác tạo kết quả String có vòng đời riêng.
- Builder được giữ lâu sau khi xử lý một nội dung rất lớn có thể tiếp tục giữ bộ đệm lớn dù length đã về 0.

Đo trên khối lượng và dạng dữ liệu thực tế trước khi chọn chiến lược tái sử dụng, thu nhỏ hoặc tạo mới. Một ví dụ in capacity chỉ giải thích cơ chế, không thay thế benchmark.

## 9. Các lỗi cần tránh

| Nhầm lẫn | Hệ quả |
| --- | --- |
| Dùng capacity làm cận khi duyệt nội dung | Đọc chỉ số nằm ngoài length |
| Coi ensureCapacity(100) là thêm 100 ký tự | Kết quả vẫn giữ nguyên length |
| Đòi capacity phải đúng bằng mức yêu cầu | Bỏ qua quy tắc tăng có phần dự phòng |
| Dùng ensureCapacity để đặt độ dài tối đa | Builder vẫn có thể phát triển thêm |
| Truyền lượng sắp append thay vì tổng cần có | Có thể không dự trữ đủ cho kết quả |
| Để phép cộng int tràn rồi truyền số âm | Yêu cầu có thể bị bỏ qua âm thầm |
| Dùng setLength để dự trữ mà không muốn NUL | Thay đổi nội dung ngoài ý định |

Khi duyệt dữ liệu, cận đúng là:

```java
for (int i = 0; i < builder.length(); i++) {
    char value = builder.charAt(i);
    // Xử lý một đơn vị char trong nội dung hiện có.
}
```

Đây là đoạn minh họa theo char UTF-16. Nếu thuật toán làm việc theo điểm mã Unicode, cần cách duyệt tương ứng; việc đổi cận thành capacity không giải quyết vấn đề đó.

## 10. Thực hành

1. Tạo builder capacity 6 và nội dung `AB`, rồi gọi ensureCapacity(5). Length vẫn 2 và capacity vẫn 6.
2. Từ capacity 6, gọi ensureCapacity(7). Theo quy tắc tăng thông thường, capacity mới là 14.
3. Sau khi xóa nội dung, quan sát rằng phần dung lượng dự trữ có thể vẫn được giữ để append tiếp.
4. Dùng ví dụ Unicode để giải thích vì sao ba điểm mã có thể cần length 4.
5. Viết phép tính tổng sức chứa cho một header, nhiều dòng và dấu kết thúc dòng; kiểm tra tràn số trước khi yêu cầu cấp phát.

Hãy dùng length để nói về **nội dung đang có**, capacity để nói về **sức chứa hiện tại**, và ensureCapacity để chuẩn bị **tổng sức chứa tối thiểu cho phần xây dựng tiếp theo**.
