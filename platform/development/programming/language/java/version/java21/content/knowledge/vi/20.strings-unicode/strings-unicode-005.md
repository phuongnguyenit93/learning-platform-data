# StringBuilder.repeat với code point hoặc CharSequence

Java 21 bổ sung hai overload `repeat` cho `StringBuilder`, giúp nối nhiều lần một Unicode code point hoặc một chuỗi ký tự vào builder hiện tại. Phương thức thay đổi chính `StringBuilder` và trả về cùng đối tượng để có thể nối chuỗi lời gọi.

Hai overload giải quyết hai nhu cầu khác nhau: lặp một ký tự Unicode đơn lẻ bằng mã code point, hoặc lặp nguyên một `CharSequence` có thể gồm nhiều ký tự/code point. Khi xử lý văn bản Unicode, cần phân biệt code point với `char` UTF-16 và với grapheme cluster (đơn vị ký tự người dùng nhìn thấy).

## 1. Hai overload repeat trong Java 21

`StringBuilder` cung cấp hai chữ ký:

```java
StringBuilder repeat(int codePoint, int count)
StringBuilder repeat(CharSequence cs, int count)
```

Cả hai phương thức đều được bổ sung trong Java 21, sửa đổi builder hiện tại và trả về tham chiếu tới chính builder đó.

| Overload | Tham số đầu tiên | Nội dung được lặp |
|---|---|---|
| `repeat(int codePoint, int count)` | Một Unicode code point | Biểu diễn ký tự của code point đó |
| `repeat(CharSequence cs, int count)` | Một chuỗi ký tự | Toàn bộ nội dung của `CharSequence` |

Ví dụ đơn giản:

```java
StringBuilder line = new StringBuilder("Tasks: ");

line.repeat('*', 5);
line.append(" done");

System.out.println(line); // Tasks: ***** done
```

Ký tự `'*'` có kiểu `char`, được mở rộng thành `int` khi gọi overload code point. Builder được sửa đổi trực tiếp; không có một `StringBuilder` mới được trả về.

## 2. Lặp một Unicode code point

Overload `repeat(int codePoint, int count)` dùng khi muốn lặp đúng một code point. Tham số `codePoint` là mã Unicode, không phải vị trí trong chuỗi và cũng không phải số lần lặp.

Với ký tự nằm trong Basic Multilingual Plane (BMP), có thể truyền trực tiếp một ký tự literal kiểu `char`:

```java
StringBuilder stars = new StringBuilder();
stars.repeat('★', 4);

System.out.println(stars); // ★★★★
```

Với ký tự ngoài BMP, chẳng hạn emoji tên lửa U+1F680, cần truyền mã code point dạng `int`:

```java
StringBuilder rockets = new StringBuilder();
rockets.repeat(0x1F680, 3);

System.out.println(rockets); // 🚀🚀🚀
System.out.println(rockets.length());
// 6: mỗi tên lửa chiếm hai UTF-16 code unit

System.out.println(rockets.codePointCount(0, rockets.length()));
// 3: có ba Unicode code point
```

Java biểu diễn một code point ngoài BMP bằng một cặp surrogate UTF-16. Vì vậy, mỗi tên lửa trong ví dụ chiếm hai `char`, mặc dù đó chỉ là một code point. `StringBuilder.length()` đếm UTF-16 code unit; `codePointCount()` đếm code point trong khoảng chỉ định.

Nếu truyền một giá trị không phải Unicode code point hợp lệ, overload này ném `IllegalArgumentException`. `count` âm cũng gây `IllegalArgumentException`. Giá trị `count` là số bản sao cần nối, không phải số byte hay số UTF-16 code unit.

### Không nhầm code point với char

Trong Java, `char` là một UTF-16 code unit có độ rộng 16 bit. Một ký tự Unicode ngoài BMP không thể được biểu diễn bằng một `char` đơn lẻ; nó cần hai code unit. Vì thế, không thể viết một char literal chứa trực tiếp emoji như `🚀`.

Hãy dùng mã code point dạng `int` cho overload thứ nhất:

```java
StringBuilder sb = new StringBuilder();
sb.repeat(0x1F680, 2); // U+1F680, hai lần
```

Không tự truyền riêng high surrogate hoặc low surrogate khi mục tiêu là lặp một ký tự bổ sung. Truyền mã Unicode đầy đủ để Java tạo đúng biểu diễn UTF-16 của code point.

## 3. Lặp một CharSequence

Overload `repeat(CharSequence cs, int count)` phù hợp khi đơn vị cần lặp có nhiều code point hoặc nhiều UTF-16 code unit. `CharSequence` có thể là `String`, `StringBuilder`, `StringBuffer` hoặc một kiểu triển khai `CharSequence` khác.

```java
StringBuilder message = new StringBuilder("Result: ");

message.repeat("OK ", 3);

System.out.println(message); // Result: OK OK OK
```

Có thể lặp một chuỗi chứa emoji hoặc ký tự kết hợp:

```java
StringBuilder labels = new StringBuilder();
labels.repeat("👩‍💻", 3);

System.out.println(labels); // 👩‍💻👩‍💻👩‍💻
```

Chuỗi `👩‍💻` gồm nhiều code point: emoji người phụ nữ, ký tự nối zero-width joiner (ZWJ) và emoji máy tính. Overload `repeat(CharSequence, int)` lặp toàn bộ chuỗi đó mỗi lần, nhờ vậy giữ nguyên chuỗi code point dùng để biểu diễn emoji ghép.

### Null trong CharSequence

Khác với nhiều phương thức nhận tham chiếu của `StringBuilder`, overload này quy định rõ rằng nếu `cs` là `null`, nó lặp bốn ký tự `"null"`:

```java
StringBuilder sb = new StringBuilder();
sb.repeat((CharSequence) null, 2);

System.out.println(sb); // nullnull
```

Nếu `count` bằng `0`, không có bản sao nào được nối. Nếu `cs` là chuỗi rỗng, kết quả cũng không tăng độ dài dù `count` lớn hơn `0`. Nếu `count` âm, phương thức ném `IllegalArgumentException`.

Không nên dựa vào việc `null` được chuyển thành chữ `"null"` như một cách xử lý dữ liệu thiếu trong nghiệp vụ. Nếu null là dữ liệu không hợp lệ, hãy kiểm tra và báo lỗi rõ ràng trước khi gọi `repeat`.

## 4. Code point và grapheme cluster không giống nhau

Một code point là một giá trị trong không gian mã Unicode. Nhưng một ký tự mà người dùng cảm nhận được trên màn hình (*grapheme cluster*) có thể gồm nhiều code point.

Ví dụ chữ `é` có thể được biểu diễn theo hai cách:

- Dạng dựng sẵn U+00E9: một code point.
- Dạng phân rã `e` (U+0065) cộng dấu sắc kết hợp U+0301: hai code point.

Nếu dùng overload code point để lặp riêng chữ `e`, dấu sắc kết hợp sẽ không được lặp theo:

```java
StringBuilder letters = new StringBuilder();
letters.repeat(0x0065, 3);

System.out.println(letters); // eee
```

Nếu muốn lặp cả chuỗi gồm chữ `e` và dấu sắc kết hợp, dùng overload `CharSequence`:

```java
String accent = "e\u0301";

StringBuilder text = new StringBuilder();
text.repeat(accent, 3);

System.out.println(text); // ééé
System.out.println(text.codePointCount(0, text.length()));
// 6 code point: mỗi cụm gồm e và dấu sắc kết hợp
```

`repeat(int, int)` lặp một code point; nó không phân tích chuỗi thành grapheme cluster. `repeat(CharSequence, int)` lặp nguyên chuỗi được truyền vào, nên phù hợp hơn khi đơn vị cần lặp gồm nhiều code point. Dù vậy, phương thức không tự chuẩn hóa Unicode và cũng không tự tìm ranh giới grapheme cluster; người gọi phải cung cấp đúng chuỗi cần lặp.

## 5. Ghép nhiều lần gọi và kết hợp với append

Vì `repeat` trả về chính builder, có thể nối nhiều thao tác để tạo mẫu văn bản:

```java
StringBuilder report = new StringBuilder();

report.repeat('=', 24)
      .append("\nJAVA 21\n")
      .repeat('-', 24)
      .append("\nCompleted: ")
      .repeat(0x2713, 3);

System.out.println(report);
```

Kết quả:

```text
========================
JAVA 21
------------------------
Completed: ✓✓✓
```

Có thể kết hợp `repeat` với `append`, `insert` hoặc các thao tác khác của `StringBuilder`. Hãy dùng `repeat` cho trường hợp nối cùng một nội dung nhiều lần; nếu mỗi phần tử cần biến đổi theo chỉ số hoặc dữ liệu riêng, vòng lặp thông thường sẽ dễ đọc và linh hoạt hơn.

## 6. So sánh với String.repeat

`String.repeat(int count)` đã có từ Java 11 và vẫn là API hiện hành. Phương thức này tạo và trả về một `String` mới chứa nội dung được lặp. Trong khi đó, `StringBuilder.repeat` có từ Java 21 và nối nội dung vào builder đang có.

```java
String token = "ab";

String repeated = token.repeat(3);
// repeated = "ababab"; token không thay đổi

StringBuilder builder = new StringBuilder("prefix:");
builder.repeat(token, 3);
// builder = "prefix:ababab"; builder được sửa đổi
```

| Tiêu chí | `String.repeat(count)` | `StringBuilder.repeat(..., count)` |
|---|---|---|
| Có từ phiên bản | Java 11 | Java 21 |
| Đơn vị lặp | Nội dung của chính String | Một code point hoặc một CharSequence |
| Kết quả | Trả về String | Trả về cùng StringBuilder |
| Thay đổi đối tượng nhận lời gọi | Không; String immutable | Có; StringBuilder mutable |
| Có thể nối tiếp vào nội dung đang xây dựng | Cần ghép kết quả với nội dung khác | Có thể gọi trên builder hiện tại |

Nếu kết quả cuối cùng cần là `String`, có thể gọi `toString()` sau khi hoàn tất builder:

```java
StringBuilder builder = new StringBuilder("ha");
builder.repeat("!", 3);

String result = builder.toString(); // ha!!!
```

## 7. Capacity, bộ nhớ và thread safety

`StringBuilder` tự tăng capacity khi nội dung vượt dung lượng hiện tại. `repeat` với count lớn có thể làm builder tăng bộ nhớ đáng kể; nếu dữ liệu đầu vào hoặc count đến từ người dùng, cần giới hạn để tránh tạo chuỗi ngoài dự kiến hoặc gây áp lực bộ nhớ.

Khi biết trước kích thước kết quả, có thể khởi tạo builder với capacity phù hợp hoặc gọi `ensureCapacity(minimumCapacity)` trước khi lặp. Capacity được tính theo UTF-16 code unit, không phải số code point:

```java
String token = "🚀";
int count = 100;

int expectedChars = token.length() * count; // 2 * 100 UTF-16 code unit
StringBuilder builder = new StringBuilder(expectedChars);
builder.repeat(token, count);
```

Đối với overload code point, một code point BMP thường thêm một UTF-16 code unit; code point ngoài BMP thêm hai. Với overload `CharSequence`, độ dài tăng theo `cs.length()` nhân với `count`.

`StringBuilder` không được đồng bộ hóa và không an toàn khi nhiều thread cùng sửa đổi một instance. Nếu cần chia sẻ một buffer mutable giữa nhiều thread, hãy đồng bộ hóa bằng cơ chế phù hợp hoặc dùng `StringBuffer` khi hợp đồng API yêu cầu buffer có đồng bộ. Thông thường, nên để mỗi task sở hữu builder riêng rồi chuyển kết quả `String` đã hoàn tất cho thread khác.

## 8. Lỗi thường gặp

| Tình huống | Kết quả | Cách xử lý |
|---|---|---|
| Truyền code point ngoài phạm vi Unicode | `IllegalArgumentException` | Kiểm tra giá trị code point trước khi gọi |
| Truyền `count` âm | `IllegalArgumentException` | Xác thực count không âm |
| Mong emoji ngoài BMP chỉ tăng `length()` một đơn vị | Sai vì emoji đó dùng cặp surrogate UTF-16 | Dùng `codePointCount()` khi cần đếm code point |
| Dùng overload code point để lặp emoji ghép hoặc chữ có dấu kết hợp | Chỉ lặp một code point, thiếu các code point còn lại | Truyền toàn bộ chuỗi qua overload `CharSequence` |
| Truyền `null` và mong có `NullPointerException` | Overload `CharSequence` lặp chữ `"null"` | Kiểm tra null tường minh nếu dữ liệu bắt buộc |
| Dùng count quá lớn | Builder có thể cần lượng bộ nhớ lớn hoặc không thể cấp phát | Giới hạn count và kích thước đầu ra |
| Nhiều thread cùng sửa một builder | Có thể xảy ra race condition hoặc dữ liệu không nhất quán | Không chia sẻ builder mutable nếu không đồng bộ |

## 9. Checklist sử dụng StringBuilder.repeat

- [ ] Chọn `repeat(int codePoint, int count)` khi đơn vị lặp là một code point.
- [ ] Chọn `repeat(CharSequence cs, int count)` khi cần lặp cả chuỗi hoặc grapheme cluster đã được xác định.
- [ ] Dùng mã code point `int` cho ký tự ngoài BMP.
- [ ] Phân biệt `StringBuilder.length()` (UTF-16 code unit) với `codePointCount()`.
- [ ] Xác thực count không âm và code point hợp lệ.
- [ ] Hiểu rằng `null` trong overload `CharSequence` được lặp như chữ `"null"`.
- [ ] Giới hạn kích thước đầu ra nếu count đến từ dữ liệu bên ngoài.
- [ ] Không chia sẻ một `StringBuilder` mutable giữa nhiều thread nếu không có đồng bộ.
- [ ] Gọi `toString()` khi cần lấy kết quả String độc lập.

## Tài liệu tham khảo

- [StringBuilder — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/StringBuilder.html): hai overload `repeat`, giá trị trả về, điều kiện `IllegalArgumentException`, xử lý null và capacity.
- [Character — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Character.html): Unicode code point, giới hạn code point và số UTF-16 code unit cần để biểu diễn một code point.
- [String — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html): `String.repeat(int)` có từ Java 11 và trả về chuỗi mới.
- [Unicode Standard Annex #29: Unicode Text Segmentation](https://www.unicode.org/reports/tr29/): khái niệm grapheme cluster và ranh giới ký tự người dùng cảm nhận được.
