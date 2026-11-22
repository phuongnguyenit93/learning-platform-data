# Quy tắc tên định danh và phân biệt chữ hoa, chữ thường trong Java

## 1. Định danh là gì?

**Định danh (identifier)** là tên lập trình viên đặt cho một thành phần trong mã Java: biến, phương thức, lớp, interface, package, tham số hoặc hằng số. Ví dụ:

~~~java
int itemCount = 3;                 // itemCount: tên biến
String customerName = "Lan";      // customerName: tên biến
~~~

Trong khai báo `public class IdentifierDemo`, `IdentifierDemo` là tên lớp. Trong `System.out.println(itemCount)`, `System`, `out`, `println`, `itemCount` là các tên được dùng để tham chiếu các thành phần khác nhau; dấu chấm `.` là ký hiệu truy cập thành viên, **không phải một phần của định danh đơn**.

**Hai câu hỏi cần tách biệt:**

1. Tên đó **có hợp lệ theo cú pháp Java** hay không?
2. Tên đó **có rõ nghĩa và phù hợp quy ước** hay không?

Một tên có thể hợp lệ nhưng khó đọc, chẳng hạn `a1` hoặc `$x`. Ngược lại, tên `item-count` nhìn giống cách đặt tên trong văn bản nhưng **không phải một định danh đơn hợp lệ** của Java.

## 2. Quy tắc ký tự đầu và ký tự tiếp theo

Một định danh thông thường phải tuân thủ quy tắc ký tự của Java:

- Ký tự đầu phải là ký tự mà Java cho phép **bắt đầu định danh** (thường là chữ cái Unicode, `_` hoặc `$`).
- Những ký tự tiếp theo có thể gồm các ký tự hợp lệ ở đầu, chữ số và một số ký tự Unicode khác được Java cho phép.
- Không được có khoảng trắng, dấu `-`, dấu `.`, dấu `@` hoặc các ký hiệu toán tử như một phần của cùng một định danh.
- Định danh không được là **từ khóa bị cấm ở vị trí đó**, literal `true`, `false`, `null`, hoặc định danh đặc biệt **`_` đứng một mình** (bị dành riêng từ Java 9).
- Java **phân biệt chữ hoa và chữ thường**: `total`, `Total` và `TOTAL` là ba tên khác nhau.

| Tên đề xuất | Hợp lệ làm tên biến thông thường? | Giải thích |
|---|---|---|
| `count` | Có | Bắt đầu bằng chữ |
| `count2` | Có | Chữ số ở vị trí sau |
| `_count` | Có | Dấu gạch dưới đầu tên được phép |
| `$count` | Có | `$` được Java cho phép, nhưng không nên lạm dụng |
| `sốLượng` | Có | Java hỗ trợ nhiều chữ cái Unicode |
| `2count` | Không | Bắt đầu bằng chữ số |
| `item-count` | Không | `-` được hiểu là toán tử trừ, không thuộc định danh |
| `item count` | Không | Có khoảng trắng |
| `item.count` | Không phải *một* định danh | Gồm hai định danh và dấu `.` |
| `_ ` | Không | `_` đơn lẻ là ký hiệu dành riêng |
| `class` | Không | Từ khóa Java |
| `true`, `null` | Không | Literal dành riêng, không dùng làm tên biến |

**Chi tiết:** Các quy tắc Unicode thực tế được mô tả bởi các phép kiểm tra tương đương `Character.isJavaIdentifierStart(int)` và `Character.isJavaIdentifierPart(int)`, nhưng **kiểm tra ký tự thôi chưa đủ**: vẫn phải loại trừ từ khóa, một số tên bị dành riêng và xem ngữ cảnh cú pháp. Không nên dùng một regex ASCII đơn giản để kết luận mọi định danh Unicode đều không hợp lệ.

## 3. Java phân biệt hoa/thường như thế nào?

Java là ngôn ngữ **case-sensitive**. Đổi một ký tự từ hoa sang thường có thể đổi sang **một định danh khác** hoặc gây lỗi vì không tìm được tên.

~~~java
int price = 100;
int Price = 200;

System.out.println(price); // 100
System.out.println(Price); // 200
~~~

Cả hai khai báo có thể cùng tồn tại trong một phạm vi vì tên khác nhau, nhưng cách đặt như vậy dễ gây nhầm lẫn và thường nên tránh.

Tương tự:

- `String` là tên lớp thư viện chuẩn; `string` không tự động được hiểu là `String`.
- `println` và `printLn` không phải một tên phương thức.
- `getName` và `getname` là hai tên khác nhau.
- `Customer` và `customer` là hai tên khác nhau (nếu được khai báo).
- `TRUE` có thể là một tên biến thông thường, còn `true` là literal boolean.

Ví dụ sai tên:

~~~java
int total = 10;
// System.out.println(Total); // Lỗi biên dịch: không có biến Total
~~~

`javac` thường báo `cannot find symbol` cho `Total`. Cách sửa là dùng **`total`** đúng với khai báo, thay vì đổi tên tùy tiện ở nhiều nơi.

**Không nhầm `case-sensitive` với cách hệ điều hành lưu tệp.** Hệ thống tệp Windows và Linux có thể xử lý chữ hoa/thường trong tên file khác nhau, nhưng **tên biến/lớp/method trong Java vẫn phân biệt hoa/thường**.

## 4. Từ khóa, literal và tên bị hạn chế

Một tên có thể dùng ký tự hoàn toàn hợp lệ nhưng vẫn bị từ chối vì trùng **từ dành riêng** hoặc xuất hiện ở **ngữ cảnh cú pháp bị hạn chế**:

- `class`, `int`, `return`, `const`, `goto` là các từ khóa dành riêng, không dùng làm tên biến.
- `true`, `false`, `null` là **literal**, không phải từ khóa, nhưng cũng không thể làm tên biến.
- `var`, `record`, `yield`, `sealed`, `permits` chịu những quy tắc theo ngữ cảnh riêng; ví dụ `int var = 7;` hợp lệ, còn `var` bị hạn chế ở vị trí tên kiểu.
- `_` đứng một mình bị dành riêng từ Java 9, nhưng `_count` và `__` là những tên hợp lệ trên Java 17.

~~~java
int _count = 5;
int __ = 6;
int var = 7;
// int _ = 8;      // Sai: _ đứng một mình.
// int class = 9;  // Sai: class là keyword.
~~~

Điểm cần nhớ khi **kiểm tra tên định danh** là tách việc kiểm tra ký tự khỏi việc kiểm tra từ dành riêng và vị trí sử dụng. Các bài về keyword theo ngữ cảnh và `_`/`const`/`goto` phân tích sâu hơn những trường hợp này.

## 5. Ví dụ Java 17 chạy được: các tên tương tự nhưng khác nhau

Tạo tệp tên chính xác **`IdentifierDemo.java`** với nội dung:

~~~java
public final class IdentifierDemo {
    private IdentifierDemo() {}

    public static void main(String[] args) {
        int count = 2;
        int Count = 5;
        int _count = 7;
        int $count = 9;
        int sốLượng = 3;

        System.out.println("count = " + count);
        System.out.println("Count = " + Count);
        System.out.println("_count = " + _count);
        System.out.println("$count = " + $count);
        System.out.println("soLuong = " + sốLượng);
    }
}
~~~

Mở terminal trong thư mục chứa file.

**Bash (Linux/macOS):**

~~~bash
java -version
javac -version
javac --release 17 -encoding UTF-8 IdentifierDemo.java
java -cp . IdentifierDemo
~~~

**PowerShell (Windows):**

~~~powershell
java -version
javac -version
javac --release 17 -encoding UTF-8 .\IdentifierDemo.java
java -cp . IdentifierDemo
~~~

Đầu ra dự kiến:

~~~text
count = 2
Count = 5
_count = 7
$count = 9
soLuong = 3
~~~

Qua chương trình này:

- `count` và `Count` không cùng biến.
- `_count` và `$count` hợp lệ về mặt cú pháp, dù không phải lựa chọn thông thường để đặt tên biến ứng dụng.
- `sốLượng` hợp lệ vì Java hỗ trợ Unicode; cờ `-encoding UTF-8` giúp compiler đọc source lưu bằng UTF-8 chính xác.
- Tên class `IdentifierDemo` phải khớp tệp nguồn `IdentifierDemo.java` vì đây là top-level `public class`. Khi chạy class mode, dùng tên class `IdentifierDemo`, không thêm `.java`.

**Khuyến nghị thực tế:** mặc dù Java cho phép nhiều ký tự Unicode, trong các dự án nhiều công cụ và nhiều quốc gia, nhóm phát triển thường thống nhất cách đặt tên dễ nhập, dễ tìm kiếm và tương thích với quy ước dự án. Đây là **quy ước**, không phải giới hạn cú pháp của Java.

## 6. Tạo lỗi có chủ đích và biết đọc thông báo compiler

Tạo một file thử tên **`BadIdentifiers.java`**:

~~~java
public class BadIdentifiers {
    public static void main(String[] args) {
        int 2items = 4;
        int total-price = 100;
        int class = 3;
        int _ = 5;
    }
}
~~~

Lệnh:

~~~bash
javac --release 17 BadIdentifiers.java
~~~

**Kết quả:** `javac` **không tạo được class file mới thành công** cho mã sai này; sẽ báo lỗi cú pháp/từ khóa. Nội dung chi tiết và số dòng báo lỗi có thể khác theo JDK.

Cách sửa những khai báo sai:

~~~java
int items2 = 4;
int totalPrice = 100;
int classNumber = 3;
int _value = 5;
~~~

Những tên sửa đều hợp lệ. Tuy nhiên, **không phải đổi tên là đủ để chương trình đúng nghiệp vụ**: vẫn cần đặt tên mang ý nghĩa thực sự của từng giá trị.

### Lỗi do sai chữ hoa/thường

~~~java
int maxScore = 100;
// System.out.println(maxscore); // Sai: maxscore chưa khai báo
System.out.println(maxScore);     // Đúng
~~~

Nếu gặp `cannot find symbol: variable maxscore`, hãy đối chiếu ký tự với dòng khai báo; không tự suy đoán Java đã chuyển tên về chữ thường.

## 7. Phân biệt quy tắc bắt buộc và quy ước đặt tên

Java cho phép nhiều tên hợp lệ, nhưng code rõ ràng nên dùng quy ước thống nhất. Các quy ước phổ biến trong Java:

| Thành phần | Quy ước thường dùng | Ví dụ |
|---|---|---|
| Biến và tham số | `lowerCamelCase` | `itemCount`, `unitPrice` |
| Method | `lowerCamelCase` | `calculateTotal()`, `isAvailable()` |
| Class và interface | `UpperCamelCase` | `OrderService`, `Runnable` |
| Hằng số `static final` | `UPPER_SNAKE_CASE` | `MAX_RETRIES`, `DEFAULT_PORT` |
| Package | Chữ thường, các phần ngăn bằng dấu `.` | `com.example.catalog` |
| Enum type | `UpperCamelCase` | `OrderStatus` |
| Enum constants | `UPPER_SNAKE_CASE` thường thấy | `PENDING`, `IN_PROGRESS` |

**Cú pháp hợp lệ không đồng nghĩa bắt buộc đặt tên theo bảng.** Ví dụ biến `MAX_RETRIES` hợp lệ dù không `static final`; nhưng dùng chữ hoa như hằng số sẽ khiến người đọc hiểu nhầm. Ngược lại, compiler không bắt mọi tên class đều bắt đầu bằng chữ hoa.

Tránh những tên quá ngắn hoặc che mất ý nghĩa (`x1`, `aaa`, `temp2`) khi không có lý do rõ ràng. Với vòng lặp rất ngắn, `i` hoặc `j` vẫn có thể chấp nhận khi ngữ cảnh hiển nhiên.

### Phân biệt tên đầy đủ và một định danh đơn

~~~java
package com.example.catalog;

public class OrderService {
    public int calculateTotal(int unitPrice, int quantity) {
        return Math.multiplyExact(unitPrice, quantity);
    }
}
~~~

`com.example.catalog` là **tên package đầy đủ**, gồm các định danh `com`, `example`, `catalog` được ngăn bằng dấu `.`. Dấu chấm không biến toàn bộ chuỗi thành một định danh đơn.

`OrderService`, `calculateTotal`, `unitPrice`, `quantity` đều là các định danh riêng, mỗi tên có vai trò trong khai báo.

## 8. Unicode và ký tự đặc biệt: dùng đúng nhưng thận trọng

Java hỗ trợ nhiều ký tự Unicode ngoài ASCII trong tên biến/lớp:

~~~java
int sốLượng = 2;
int giá = 15;
int thànhTiền = sốLượng * giá;
System.out.println(thànhTiền); // 30
~~~

Nếu nguồn lưu UTF-8, hãy biên dịch với `javac -encoding UTF-8` (khi cần có thể kết hợp `--release 17`). Việc console hiển thị Unicode đúng còn phụ thuộc terminal và cấu hình hệ thống; **khả năng đọc tên trong source** và **khả năng hiển thị output** là hai chuyện khác nhau.

Không giả định **mọi ký tự nhìn giống chữ** đều được Java chấp nhận hoặc được chuẩn hóa giống nhau. Ví dụ một chữ có dấu có thể có những cách biểu diễn Unicode khác nhau; việc dùng không nhất quán dễ làm mã khó tìm kiếm và review. Trong đội nhóm, dùng bộ ký tự/quy ước nhất quán có thể quan trọng hơn việc tận dụng mọi ký tự Java cho phép.

### Vì sao Java cho phép `$`?

Ký tự `$` hợp lệ trong tên, nhưng **quy ước Java khuyến khích hạn chế sử dụng trong định danh do lập trình viên tạo**; một số công cụ sinh mã hoặc tên class lồng nhau cũng có thể dùng `$`. Người học nên ưu tiên `itemCount` hơn `$itemCount` để mã dễ đọc và tránh nhập nhằng với tên do công cụ sinh ra.

## 9. Cùng tên, khác phạm vi: đừng nhầm với phân biệt hoa/thường

Trong **một block**, không thể khai báo hai biến cục bộ trùng tên:

~~~java
int count = 1;
// int count = 2; // Sai: biến cục bộ count đã được định nghĩa
int Count = 2;    // Đúng về cú pháp, nhưng dễ gây nhầm
~~~

Ngoài tên, Java còn xét **phạm vi (scope)** và **ngữ cảnh**. Một tham số method, field và biến cục bộ có thể có những quy tắc đặt tên/trùng tên khác nhau.

Ví dụ về che khuất tên field:

~~~java
class Box {
    private int size = 10;

    void show(int size) {
        System.out.println(size);      // Tham số size
        System.out.println(this.size); // Field của object
    }
}
~~~

Khi gọi `new Box().show(4)`, sẽ in `4` rồi `10`. Cả hai đều tên `size`, nhưng `this.size` chỉ rõ field. Trường hợp này là **name shadowing**, không phải cơ chế Java tự bỏ qua chữ hoa/chữ thường.

## 10. Những lỗi thực tế hay gặp

| Triệu chứng | Vấn đề cần kiểm tra | Cách sửa |
|---|---|---|
| `cannot find symbol` ở tên biến | Gõ sai chữ hoa/thường, sai chính tả, nằm ngoài scope | Đối chiếu tên khai báo và phạm vi |
| `';' expected` hoặc lỗi cú pháp gần tên | Tên có dấu `-`, khoảng trắng hoặc ký hiệu lạ | Dùng định danh hợp lệ, ví dụ `totalPrice` |
| `<identifier> expected` | Tên sai vị trí, bắt đầu bằng số hoặc từ khóa | Chọn tên hợp lệ theo Java |
| `as of release 9, '_' is a keyword` (hoặc thông báo tương đương) | Dùng `_` đơn lẻ | Đổi thành `_value` hoặc tên có nghĩa |
| `variable x is already defined` | Khai báo hai biến cùng tên tại vị trí cấm trùng | Đổi tên có ý nghĩa hoặc bỏ khai báo dư |
| `class IdentifierDemo is public, should be declared ...` | Tên source và top-level public class không khớp | Đặt tệp `IdentifierDemo.java` |
| Source chứa tên Unicode biên dịch sai | Encoding không khớp | Lưu UTF-8 và dùng `-encoding UTF-8` |
| Class/method tên khác hoa thường bị thiếu | Java phân biệt `Demo` và `demo`, `run` và `Run` | Sửa đúng tên ở khai báo/lời gọi |

Khi sửa một lỗi, **đừng thay hàng loạt tên chỉ để compiler im lặng**. Đổi tên class, method hoặc public API còn có thể yêu cầu cập nhật những nơi tham chiếu và tên file tương ứng.

## 11. Bài tập có đáp án

### Bài A — tên nào hợp lệ?

Phân loại các tên sau khi dùng làm **tên biến** trong Java 17: `age`, `Age`, `age2`, `2age`, `_age`, `_`, `$age`, `class`, `true`, `total-price`.

**Đáp án:** hợp lệ: `age`, `Age`, `age2`, `_age`, `$age`. Không hợp lệ: `2age` (đầu là số), `_` (dành riêng), `class` (từ khóa), `true` (literal), `total-price` (chứa dấu trừ).

### Bài B — dự đoán đầu ra

~~~java
int score = 10;
int Score = 20;
System.out.println(score + Score);
~~~

**Đáp án:** `30`. `score` và `Score` là hai biến riêng, không phải cùng một biến viết khác kiểu.

### Bài C — sửa lỗi do case-sensitive

~~~java
String customerName = "Lan";
// System.out.println(customername);
~~~

**Đáp án:** dùng `customerName` trong lời gọi `println`, hoặc thực hiện đổi tên đồng nhất ở mọi nơi. Không phải Java tự hiểu `customername` trùng `customerName`.

### Bài D — đặt tên rõ nghĩa

Đổi ba tên `a`, `b`, `c` trong phép tính tiền hàng để người đọc đoán được ý nghĩa.

**Đáp án gợi ý:** `unitPrice`, `quantity`, `subtotal`. Tên có nghĩa phản ánh dữ liệu và công thức, dù bản thân compiler không bắt buộc.

### Bài E — Unicode và quy tắc đặt tên

Đoạn `int sốLượng = 2;` có sai chỉ vì tên chứa dấu tiếng Việt không?

**Đáp án:** Không; đó là định danh hợp lệ. Nên lưu mã nguồn bằng UTF-8, đồng bộ encoding và quy ước nhóm. Không cần đổi sang ASCII chỉ để hợp lệ về cú pháp.

## 12. Checklist hoàn thành

- [ ] Giải thích được định danh là gì và khác dấu phân cách/toán tử.
- [ ] Biết chữ số được đứng sau, nhưng không phải ký tự bắt đầu thông thường của tên.
- [ ] Phân biệt `count`, `Count`, `COUNT` trong Java.
- [ ] Nhận ra từ khóa, literal `true`/`false`/`null` và `_` đơn lẻ không hợp lệ làm tên biến.
- [ ] Biết `_` và `$` có thể là **một phần** của tên, nhưng cần cân nhắc quy ước.
- [ ] Biết Java hỗ trợ định danh Unicode, không giới hạn trong `A-Z`/`a-z`.
- [ ] Áp dụng `lowerCamelCase`, `UpperCamelCase`, `UPPER_SNAKE_CASE` đúng vai trò theo quy ước.
- [ ] Biên dịch và chạy `IdentifierDemo.java` trên JDK 17+; kết quả đúng bảng dự kiến.
- [ ] Tự tìm lỗi `cannot find symbol` do gõ sai chữ hoa/thường và lỗi đặt tên không hợp lệ.
- [ ] Phân biệt **sai tên**, **trùng tên trong scope** và **che khuất tên field**.

**Kết luận:** Một định danh Java phải dùng ký tự hợp lệ, không đụng tên bị dành riêng trong ngữ cảnh cú pháp, và được viết **đúng chữ hoa/chữ thường**. Quy tắc ngôn ngữ cho biết tên nào có thể biên dịch; quy ước đặt tên giúp chương trình rõ nghĩa, nhất quán và dễ bảo trì.