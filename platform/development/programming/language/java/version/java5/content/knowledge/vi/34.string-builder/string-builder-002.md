# Khởi tạo StringBuilder với nội dung hoặc sức chứa dự kiến

## 1. Hai quyết định khác nhau lúc tạo bộ dựng chuỗi

StringBuilder giữ một dãy ký tự có thể thay đổi. Khi tạo đối tượng, cần phân biệt:

- **Nội dung ban đầu:** những ký tự đã có trong dãy.
- **Sức chứa ban đầu (capacity):** dung lượng dành sẵn để dãy phát triển mà chưa cần tăng bộ đệm.

Ví dụ:

```java
StringBuilder withText = new StringBuilder("Java");
StringBuilder reserved = new StringBuilder(100);
```

`withText` đã có nội dung `Java`. `reserved` vẫn rỗng; số 100 không phải nội dung và cũng không phải độ dài đang sử dụng.

Có thể hình dung:

```text
length   = phần dãy đã có nội dung hợp lệ
capacity = sức chứa hiện có, bao gồm phần chưa sử dụng
```

Sức chứa là một chi tiết phục vụ việc xây dựng chuỗi. Người dùng kết quả chỉ nhìn thấy các ký tự từ vị trí 0 đến `length() - 1`, không nhìn thấy phần dự trữ.

## 2. Chọn constructor

| Cách tạo | Nội dung ban đầu | length ban đầu | capacity ban đầu |
| --- | --- | --- | --- |
| `new StringBuilder()` | Rỗng | 0 | 16 |
| `new StringBuilder(n)` | Rỗng | 0 | n |
| `new StringBuilder(text)` với String | Bản sao nội dung text | `text.length()` | `text.length() + 16` |
| `new StringBuilder(sequence)` với CharSequence | Nội dung của sequence tại lúc tạo | `sequence.length()` | `sequence.length() + 16` |

Các giá trị trong bảng áp dụng khi tạo thành công với đầu vào hợp lệ. Constructor nhận sức chứa không âm; giá trị âm gây `NegativeArraySizeException`. Đầu vào String hoặc CharSequence là null gây `NullPointerException`.

Các constructor này vẫn được dùng trong Java hiện hành. Tham khảo [StringBuilder constructors](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/StringBuilder.html#constructor-summary).

Sức chứa ban đầu không phải độ dài tối đa. Nếu thêm dữ liệu vượt sức chứa, StringBuilder tự tăng dung lượng khi có thể cấp phát bộ nhớ. `new StringBuilder(100)` không có nghĩa “chỉ được nhập tối đa 100 ký tự”.

## 3. Quan sát nội dung, length và capacity

Lưu thành `BuilderConstructionDemo.java`:

```java
public class BuilderConstructionDemo {
    private static void show(String label, StringBuilder builder) {
        System.out.println(label + ": text=[" + builder
                + "], length=" + builder.length()
                + ", capacity=" + builder.capacity());
    }

    public static void main(String[] args) {
        show("default", new StringBuilder());
        show("reserved", new StringBuilder(32));
        show("seeded", new StringBuilder("Java"));
        show("empty text", new StringBuilder(""));
        show("zero capacity", new StringBuilder(0));

        StringBuilder small = new StringBuilder(2);
        small.append("ABCDE");
        System.out.println("grown text = " + small);
        System.out.println("grown length = " + small.length());
        System.out.println("capacity covers length = "
                + (small.capacity() >= small.length()));
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```shell
javac -encoding UTF-8 BuilderConstructionDemo.java
java BuilderConstructionDemo
```

Stdout chính xác:

```text
default: text=[], length=0, capacity=16
reserved: text=[], length=0, capacity=32
seeded: text=[Java], length=4, capacity=20
empty text: text=[], length=0, capacity=16
zero capacity: text=[], length=0, capacity=0
grown text = ABCDE
grown length = 5
capacity covers length = true
```

Điểm cần quan sát:

1. Dự trữ 32 đơn vị vẫn cho một dãy rỗng.
2. Khởi tạo bằng `Java` vừa đặt nội dung, vừa có thêm phần sức chứa dự phòng.
3. Sức chứa bằng 0 là hợp lệ; không bắt buộc mọi builder phải có sức chứa dương ngay từ đầu.
4. Builder ban đầu chứa được 2 đơn vị vẫn nhận được nội dung dài hơn. Chương trình kiểm tra bất biến `capacity() >= length()`, thay vì dùng một con số tăng trưởng làm quy tắc nghiệp vụ.

Đừng dùng phần sức chứa còn trống như thể đã là nội dung. Sau `new StringBuilder(32)`, gọi `charAt(0)` vẫn sai vì length bằng 0.

## 4. Khởi tạo bằng nội dung là sao chép nội dung

Constructor nhận CharSequence cho phép dùng String, StringBuilder hoặc một nguồn ký tự khác phù hợp. Builder mới có nội dung riêng; nó không trở thành một “cửa sổ trực tiếp” nhìn vào builder nguồn.

Lưu thành `BuilderSeedDemo.java`:

```java
public class BuilderSeedDemo {
    public static void main(String[] args) {
        StringBuilder source = new StringBuilder("draft");
        StringBuilder copy = new StringBuilder(source);

        source.append("-changed");
        copy.append("-copy");

        System.out.println("source = " + source);
        System.out.println("copy = " + copy);

        StringBuilder numericCapacity = new StringBuilder(42);
        StringBuilder numericText = new StringBuilder("42");
        System.out.println("int argument length = "
                + numericCapacity.length());
        System.out.println("string argument text = " + numericText);

        StringBuilder charAsCapacity = new StringBuilder('A');
        StringBuilder charAsContent = new StringBuilder().append('A');
        System.out.println("char argument length = "
                + charAsCapacity.length());
        System.out.println("char argument capacity = "
                + charAsCapacity.capacity());
        System.out.println("appended char = " + charAsContent);

        String smile = "\uD83D\uDE00";
        StringBuilder unicode = new StringBuilder(smile);
        System.out.println("UTF-16 length = " + unicode.length());
        System.out.println("code points = "
                + unicode.codePointCount(0, unicode.length()));
        System.out.println("Unicode initial capacity = "
                + unicode.capacity());
    }
}
```

Chạy:

```shell
javac -encoding UTF-8 BuilderSeedDemo.java
java BuilderSeedDemo
```

Stdout chính xác:

```text
source = draft-changed
copy = draft-copy
int argument length = 0
string argument text = 42
char argument length = 0
char argument capacity = 65
appended char = A
UTF-16 length = 2
code points = 1
Unicode initial capacity = 18
```

### Hai lỗi chọn overload dễ bỏ sót

`new StringBuilder(42)` gọi constructor nhận int: builder rỗng với sức chứa 42. Muốn nội dung `42`, dùng chuỗi `"42"`, hoặc tạo builder rồi `append(42)`.

StringBuilder không có constructor nhận char làm nội dung. Ký tự `'A'` được mở rộng thành int có giá trị 65, nên `new StringBuilder('A')` dự trữ sức chứa 65. Muốn một ký tự đầu tiên, dùng `new StringBuilder().append('A')` hoặc khởi tạo bằng String `"A"`.

Sự khác biệt xuất phát từ kiểu của đối số, không phải hình thức giá trị mà người viết muốn hiển thị.

### Đơn vị đếm là UTF-16, không phải byte

Dãy `\uD83D\uDE00` trong ví dụ là một điểm mã Unicode ngoài BMP, được biểu diễn bằng hai đơn vị mã UTF-16. Bởi vậy length bằng 2, dù số điểm mã là 1.

Không đồng nhất:

- số byte của văn bản UTF-8;
- số đơn vị mã UTF-16 mà length/capacity sử dụng;
- số điểm mã Unicode;
- số ký tự mà người dùng nhìn thấy.

Một ký tự hiển thị cũng có thể được cấu thành từ nhiều điểm mã. Khi dự trữ cho các String đã có, tổng `String.length()` là cơ sở phù hợp với đơn vị của StringBuilder. Xem [String.length()](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html#length()).

Không suy ra số byte bộ nhớ bằng cách nhân capacity với một hằng số rồi coi đó là hợp đồng của API. Cách lưu trữ nội bộ là chi tiết triển khai và có thể phụ thuộc nội dung.

## 5. Ước lượng sức chứa để giảm nhu cầu tăng bộ đệm

Nếu biết trước cấu trúc đầu ra, có thể cộng:

```text
độ dài tiền tố
+ tổng độ dài các phần nội dung
+ tổng độ dài dấu phân cách
+ độ dài hậu tố, nếu có
```

Ví dụ có ba tên, ngăn bằng `, ` và có tiền tố `users=`. Số dấu phân cách là số phần trừ 1 khi danh sách không rỗng.

Lưu thành `BuilderCapacityPlanDemo.java`:

```java
public class BuilderCapacityPlanDemo {
    public static void main(String[] args) {
        String prefix = "users=";
        String separator = ", ";
        String[] users = {"An", "Binh", "Chi"};

        int expected = prefix.length();
        for (String user : users) {
            expected = Math.addExact(expected, user.length());
        }

        int separatorCount = Math.max(0, users.length - 1);
        int separatorLength = Math.multiplyExact(
                separatorCount, separator.length());
        expected = Math.addExact(expected, separatorLength);

        StringBuilder builder = new StringBuilder(expected);
        builder.append(prefix);

        for (int i = 0; i < users.length; i++) {
            if (i > 0) {
                builder.append(separator);
            }
            builder.append(users[i]);
        }

        System.out.println("expected = " + expected);
        System.out.println("text = " + builder);
        System.out.println("length = " + builder.length());
        System.out.println("capacity = " + builder.capacity());
    }
}
```

Chạy:

```shell
javac -encoding UTF-8 BuilderCapacityPlanDemo.java
java BuilderCapacityPlanDemo
```

Stdout chính xác:

```text
expected = 19
text = users=An, Binh, Chi
length = 19
capacity = 19
```

Cách tính dùng Math.addExact và Math.multiplyExact để phát hiện tràn số int thay vì âm thầm tạo ra một ước lượng sai. Trong ví dụ nhỏ không có nguy cơ tràn; mục đích là chỉ ra nơi cần bảo vệ khi công thức sức chứa được áp dụng cho dữ liệu lớn.

Đây là ví dụ minh họa cách tính, không phải bằng chứng benchmark rằng mọi chương trình phải tính chính xác trước khi nối chuỗi.

Nếu chỉ cần nối các phần với dấu phân cách, `String.join()` có thể biểu đạt yêu cầu ngắn hơn. Chọn StringBuilder khi cần xây dựng nội dung theo nhiều bước; không dùng tính toán capacity để làm phức tạp một trường hợp đơn giản không có nhu cầu đó.

## 6. Vừa có nội dung đầu, vừa muốn dự trữ thêm

Không có constructor dạng `StringBuilder(text, capacity)`. Có thể chọn một trong hai cách:

```java
String prefix = "Report: ";
int expectedFinalLength = 200;

StringBuilder first = new StringBuilder(expectedFinalLength);
first.append(prefix);

StringBuilder second = new StringBuilder(prefix);
second.ensureCapacity(expectedFinalLength);
```

Đây là đoạn minh họa độc lập về cách khởi tạo. Cả hai builder đều bắt đầu với nội dung `Report: ` và có đủ sức chứa cho mức dự kiến ở ví dụ.

`ensureCapacity(n)` bảo đảm ít nhất mức yêu cầu khi cần tăng, không đặt length và không bảo đảm capacity sau lời gọi phải đúng bằng n. Nếu capacity hiện tại đã đủ, không cần tăng.

Đây khác với `setLength(n)`. Khi tăng length, StringBuilder thêm các ký tự NUL `\u0000` vào phần nội dung mới. Nó không chỉ đặt chỗ trống để dùng sau.

Đoạn minh họa:

```java
StringBuilder builder = new StringBuilder(100);
System.out.println(builder.length()); // 0

builder.setLength(3);
System.out.println(builder.length()); // 3
System.out.println((int) builder.charAt(0)); // 0: ký tự NUL
```

Nếu muốn đặt chỗ trước khi append, dùng constructor sức chứa hoặc ensureCapacity. Không dùng setLength để giả lập việc đặt chỗ rồi vô tình tạo ra các ký tự NUL trong kết quả.

## 7. Chọn mức dự trữ hợp lý

| Tình huống | Lựa chọn thường phù hợp |
| --- | --- |
| Chưa có nội dung, không biết kích thước | `new StringBuilder()` |
| Chưa có nội dung, biết tương đối kích thước | `new StringBuilder(expected)` |
| Có chuỗi đầu và chỉ thêm ít nội dung | `new StringBuilder(prefix)` |
| Có chuỗi đầu, biết đầu ra sẽ lớn hơn nhiều | Tạo với expected rồi append prefix, hoặc ensureCapacity |
| Một biểu thức ghép ngắn, cố định | Dùng cách ghép dễ đọc; không bắt buộc builder |

Ước lượng thấp vẫn cho phép kết quả đúng nếu có đủ bộ nhớ để builder tăng sức chứa. Ước lượng quá cao có thể lãng phí bộ nhớ, đặc biệt khi nhiều builder cùng tồn tại.

Không dùng kích thước do người dùng nhập trực tiếp để cấp phát rất lớn nếu ứng dụng chưa có giới hạn phù hợp. Một capacity không âm và nằm trong phạm vi int không bảo đảm JVM có thể cấp phát bộ nhớ tương ứng. Tràn công thức, giới hạn mảng và thiếu bộ nhớ là những vấn đề khác nhau.

Đừng dựa vào một mẹo như “luôn dự trữ một triệu ký tự” hoặc “luôn tính đúng từng đơn vị”. Nếu khối lượng nối chuỗi thực sự là điểm nghẽn, đo trên dữ liệu đại diện rồi chọn mức ước lượng phù hợp. Capacity không phải cam kết rằng toàn bộ quá trình sẽ không cấp phát thêm bất kỳ đối tượng nào.

## 8. Null và chính sách nội dung đầu vào

Phải quyết định ý nghĩa của null trước khi tạo builder:

```java
String prefix = null;
StringBuilder builder = new StringBuilder(prefix); // NullPointerException
```

Đây là đoạn minh họa lỗi có chủ đích. Constructor không tự coi null là chuỗi rỗng.

Nếu nghiệp vụ cho phép không có tiền tố, thể hiện chính sách đó rõ ràng:

```java
StringBuilder builder = new StringBuilder(prefix == null ? "" : prefix);
```

Nếu null là dữ liệu sai, hãy từ chối ở ranh giới thích hợp thay vì âm thầm chuyển thành rỗng.

Cũng đừng đồng nhất constructor với `append((String) null)`: append kiểu String sẽ thêm chữ `null`. Khi học cách tạo builder, luôn phân biệt “không có tham chiếu chuỗi”, “chuỗi rỗng” và “chuỗi gồm bốn ký tự null”.

## 9. Tự kiểm tra

1. Với `new StringBuilder(10)`, length là 0; muốn nội dung `10`, phải truyền String hoặc append số.
2. Với `new StringBuilder("abc")`, length là 3 và capacity ban đầu là 19.
3. Với một String chứa điểm mã ngoài BMP trong ví dụ, tính capacity từ length UTF-16, không từ số điểm mã.
4. Trong ví dụ danh sách tên, thay danh sách bằng mảng rỗng. Không tạo số dấu phân cách âm; kết quả chỉ còn tiền tố.
5. Thay đổi builder nguồn sau khi tạo bản sao bằng constructor CharSequence. Bản sao không tự thay đổi theo nguồn.
6. Dự trữ nhiều hơn không làm các vị trí mới trở thành nội dung có thể đọc bằng charAt.

Chọn constructor dựa trên điều thực sự muốn thiết lập: **đưa ký tự nào vào ngay từ đầu** và **dành trước bao nhiêu sức chứa để xây dựng tiếp**.
