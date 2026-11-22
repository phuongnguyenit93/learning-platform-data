# Đọc thông báo `javac` và sửa từ lỗi gốc (Java 17+)

## 1. Mục tiêu

Khi biên dịch Java bằng `javac`, một lỗi trong mã nguồn đôi khi tạo ra nhiều thông báo lỗi ở những dòng khác nhau. Kỹ năng cần có là **đọc được thông báo, xác định nguyên nhân ban đầu, sửa nguyên nhân ấy, rồi biên dịch lại**; không sửa máy móc mọi dòng được đánh dấu nếu chúng chỉ là hậu quả.

Sau bài này, bạn có thể đọc vị trí lỗi, thông điệp và các chi tiết `symbol`/`location`; phân biệt lỗi cú pháp, định danh, kiểu, truy cập, dependency với ngoại lệ lúc chạy; dùng `javac` để tái hiện và kiểm tra bản sửa trên JDK 17+.

## 2. Một thông báo `javac` cho biết gì?

Ví dụ mã nguồn **có lỗi chủ đích** trong tệp `SumDemo.java`:

```java
public class SumDemo {
    public static void main(String[] args) {
        int left = 3;
        int right = 4;
        int sum = left + right;
        System.out.println(smu);
    }
}
```

Biên dịch bằng:

```sh
javac -encoding UTF-8 SumDemo.java
```

Trình biên dịch sẽ báo không tìm thấy biến `smu` vì chương trình khai báo tên `sum`. Một mẫu thông báo minh họa (dấu cách, dấu `^`, số dòng, từ ngữ chi tiết có thể thay đổi theo JDK):

```text
SumDemo.java:6: error: cannot find symbol
        System.out.println(smu);
                           ^
  symbol:   variable smu
  location: class SumDemo
1 error
```

Các thành phần cần đọc:

| Thành phần | Cách hiểu |
| --- | --- |
| `SumDemo.java:6` | Tệp và dòng liên quan đến vị trí trình biên dịch phát hiện lỗi |
| `error` | Mức độ chẩn đoán: lỗi cản trở biên dịch thành công |
| `cannot find symbol` | Không phân giải được tên trong ngữ cảnh đó |
| Dòng mã và dấu `^` | Vùng/token mà `javac` đang chỉ ra; không bảo đảm đó là chỗ nguyên nhân bắt đầu |
| `symbol: variable smu` | Loại thành viên hoặc định danh đang được tìm |
| `location: class SumDemo` | Ngữ cảnh mà trình biên dịch đang tra cứu |
| `1 error` | Số lỗi được liệt kê ở cuối đợt biên dịch này |

Với lỗi khác, `javac` có thể cung cấp `required`/`found`, chữ ký phương thức, overload ứng viên, lý do không áp dụng được hoặc đường dẫn source khác. Đây là dữ liệu giúp so sánh **mã hiện tại** với **điều compiler yêu cầu**.

Lưu ý: số dòng thường là nơi trình biên dịch *nhận ra* sự cố, không nhất thiết là dòng cần sửa. Chẳng hạn thiếu `;` ở cuối dòng trước có thể khiến token đầu dòng sau bị đánh dấu.

## 3. Quy trình 6 bước sửa từ lỗi gốc

1. **Tái hiện lỗi trên một lệnh biên dịch rõ ràng.** Xác nhận đúng JDK, đúng thư mục và đúng tập tệp được biên dịch. Giữ lại thông báo đầy đủ, không chỉ sao chép một dòng `error`.
2. **Đọc nhóm lỗi đầu tiên trong ngữ cảnh.** Bắt đầu từ lỗi cú pháp hoặc lỗi định danh xuất hiện sớm; xem vài dòng trước và sau vị trí `^`, dấu ngoặc, dấu nháy, tên khai báo, `package` và `import`.
3. **Tìm nguyên nhân chung nhỏ nhất.** Một dấu `}` thiếu có thể khiến nhiều khai báo bị hiểu sai; một tên kiểu chưa biên dịch hoặc một import sai có thể kéo theo nhiều lỗi sử dụng kiểu ấy.
4. **Sửa một nguyên nhân thực sự**, giữ các thay đổi tối thiểu. Tránh đổi hàng loạt tên hoặc thêm ép kiểu/import theo phỏng đoán chỉ để giảm số lượng thông báo.
5. **Chạy lại đúng lệnh `javac`.** Đọc tập thông báo mới; lỗi kéo theo có thể tự biến mất. Nếu còn lỗi độc lập, xử lý lần lượt.
6. **Chạy bằng `java` sau khi biên dịch thành công**, kiểm tra output/hành vi. `javac` biên dịch được không có nghĩa chương trình không gặp ngoại lệ hay đúng logic.

Đây là phương pháp ưu tiên, không phải quy luật rằng *lỗi được in đầu tiên luôn là lỗi gốc*: việc compiler phục hồi sau lỗi cú pháp, thứ tự biên dịch nhiều tệp và lỗi ở dependency có thể làm chẩn đoán xuất hiện tại nơi hậu quả. Hãy dựa vào bằng chứng và thử một bản sửa nhỏ rồi biên dịch lại.

## 4. Sửa ví dụ `cannot find symbol` cho đúng

Trong `SumDemo.java` ở trên, đổi `smu` thành `sum`. Toàn bộ chương trình hợp lệ:

```java
public class SumDemo {
    public static void main(String[] args) {
        int left = 3;
        int right = 4;
        int sum = left + right;
        System.out.println("sum=" + sum);
    }
}
```

Tạo thư mục `out` một lần rồi biên dịch, chạy từ thư mục chứa `SumDemo.java`. Các lệnh sau dùng được trong PowerShell, CMD, bash:

```sh
mkdir out
javac -encoding UTF-8 --release 17 -d out SumDemo.java
java -cp out SumDemo
```

**Output chính xác của lệnh `java`:**

```text
sum=7
```

- `-encoding UTF-8`: đọc nguồn với mã hóa UTF-8, tránh lỗi khi có ký tự tiếng Việt.
- `--release 17`: biên dịch theo ngôn ngữ và API Java 17 (khi trình biên dịch hỗ trợ bản đích đó). Dùng JDK 17+ để chạy các lệnh trong bài.
- `-d out`: đặt file `.class` vào thư mục đầu ra; thư mục này phải tồn tại trước.
- `-cp out`: thêm thư mục chứa lớp đã biên dịch vào classpath lúc chạy.

`javac` biên dịch thành công thường **không in gì**. Chuỗi `sum=7` là stdout của chương trình, không phải thông báo của compiler. Trong quy trình sửa lỗi, chỉ chạy `java` sau khi lệnh `javac` thành công để tránh vô tình chạy file `.class` cũ.

## 5. Các nhóm lỗi thường gặp và cách tìm gốc

| Dấu hiệu trong diagnostic | Gốc cần kiểm tra | Hướng sửa đúng |
| --- | --- | --- |
| `';' expected`, `')' expected`, `illegal start of expression` | Thiếu dấu `;`, `)`, `}`, cấu trúc cú pháp sai hoặc dấu nháy chưa đóng | Đọc ngược vài dòng, cân cặp dấu ngoặc, sửa cú pháp đầu tiên |
| `reached end of file while parsing` | Thường thiếu dấu đóng `}` hoặc cấu trúc chưa hoàn tất | So sánh các khối `class`, method, `if`, vòng lặp |
| `cannot find symbol` | Tên sai chính tả/chữ hoa-thường, chưa khai báo, ngoài scope, thiếu kiểu/thư viện | Kiểm tra khai báo, phạm vi, tên đầy đủ, package và classpath |
| `package ... does not exist` | Sai `import`, thiếu dependency/source trong lệnh biên dịch, module chưa khả dụng | Kiểm tra package thực, JAR/source, classpath/module path |
| `incompatible types` | Gán/return/truyền tham số không tương thích | So sánh kiểu nguồn và kiểu đích, sửa dữ liệu hoặc API |
| `method ... cannot be applied`, `no suitable method found` | Số lượng, thứ tự, kiểu tham số hoặc overload không phù hợp | Đối chiếu chữ ký phương thức với lời gọi |
| `has private access`, `is not public ... cannot be accessed` | Vi phạm mức truy cập `private`, package-private, `protected` hoặc kiểu không public | Sửa thiết kế API/phạm vi đúng chủ đích, không chỉnh access tùy tiện |
| `class ... is public, should be declared in a file named ...` | Tên file không khớp tên kiểu top-level public | Đổi tên file cho khớp lớp public |
| `duplicate class` hoặc định nghĩa trùng | Nhiều nguồn biên dịch cùng tên kiểu đầy đủ hoặc khai báo trùng | Kiểm tra các file/class và cấu hình build |
| `bad class file`, `class file has wrong version` | Thư viện được biên dịch bằng Java mới hơn phiên bản compiler/runtime đang dùng hoặc file không phù hợp | Kiểm tra JDK thực tế, phiên bản dependency, build output |

Các câu ở cột đầu là **dạng thông báo thường gặp**, không phải chuỗi bảo đảm đúng từng ký tự trên mọi JDK. Đừng xác định cách sửa chỉ bằng từ khóa: đọc cả kiểu, tham số, scope và vị trí.

### 5.1. Thiếu dấu khiến lỗi xuất hiện ở dòng sau

Ví dụ **cố ý sai, không chạy được**:

```java
public class SyntaxDemo {
    public static void main(String[] args) {
        int count = 2
        System.out.println(count);
    }
}
```

Gốc là thiếu `;` sau `2`, dù `javac` có thể trỏ đến phần đầu lệnh `System.out.println` bên dưới. Thêm `;`, không xóa lệnh `println` chỉ vì nó bị đánh dấu.

Phiên bản sửa:

```java
public class SyntaxDemo {
    public static void main(String[] args) {
        int count = 2;
        System.out.println("count=" + count);
    }
}
```

Lưu trong `SyntaxDemo.java`:

```sh
javac -encoding UTF-8 --release 17 -d out SyntaxDemo.java
java -cp out SyntaxDemo
```

Output:

```text
count=2
```

### 5.2. Sai kiểu và lời gọi phương thức

Đoạn **cố ý sai** sau làm phát sinh lỗi kiểu:

```java
String quantity = "5";
int next = quantity + 1; // String + int tạo String, không gán trực tiếp cho int
```

Nếu `quantity` biểu diễn số nguyên hợp lệ, sửa ở nguồn dữ liệu: `int quantity = Integer.parseInt("5"); int next = quantity + 1;`. Nếu mục tiêu là nối chuỗi, biến kết quả phải có kiểu `String`. Cách sửa tùy **ý nghĩa** dữ liệu; ép kiểu bừa bãi không giải quyết được khác biệt giữa số và chuỗi.

Với lời gọi `Math.max(2, "3")`, một đối số `String` không đáp ứng overload dành cho số. Lỗi gốc là truyền sai kiểu, không phải thiếu `import java.lang.Math` (kiểu `Math` đã thuộc `java.lang`). Thay `"3"` bằng số `3` khi muốn tính số lớn hơn.

### 5.3. Mã nguồn nhiều tệp và lỗi dây chuyền

Giả sử `src/lesson/Calculator.java` có khai báo:

```java
package lesson;

public class Calculator {
    public static int doubleOf(int n) {
        return n * 2;
    }
}
```

Và `src/lesson/App.java`:

```java
package lesson;

public class App {
    public static void main(String[] args) {
        System.out.println("value=" + Calculator.doubleOf(3));
    }
}
```

Biên dịch hai tệp vào cùng output, rồi chạy:

```sh
javac -encoding UTF-8 --release 17 -d out src/lesson/Calculator.java src/lesson/App.java
java -cp out lesson.App
```

Output:

```text
value=6
```

Nếu nhầm `package lesson;` thành `package lessons;` ở một tệp, hoặc loại `Calculator.java` khỏi nguồn biên dịch mà không cung cấp lớp tương ứng trên classpath, các lỗi kiểu/định danh trong `App.java` có thể là hậu quả. Kiểm tra **package thực tế, tên đầy đủ của kiểu, nguồn/JAR và cấu hình lệnh** trước khi sửa từng lần sử dụng `Calculator`.

Khi đang sửa dependency, hãy biên dịch lại toàn bộ phần có liên quan để tránh dùng `.class` cũ. Với dự án lớn, để Maven/Gradle quản lý classpath và source set, nhưng vẫn cần đọc lỗi `javac` ở bước compile thật sự.

## 6. Dùng tùy chọn `javac` để thu hẹp chẩn đoán

Một số tùy chọn hữu ích với Java 17+:

```sh
javac -encoding UTF-8 --release 17 -Xdiags:verbose -Xmaxerrs 20 -d out SumDemo.java
```

- `-Xdiags:verbose`: yêu cầu mức diagnostic chi tiết hơn; hữu ích với suy luận generic hoặc overload. Đây là tùy chọn bổ sung của `javac`.
- `-Xmaxerrs 20`: giới hạn số lỗi được in trong một lần gọi; **không** sửa lỗi và có thể ẩn thông báo sau ngưỡng.
- `-Xlint:all`: bật nhiều cảnh báo hữu ích (unchecked, deprecation, raw types, v.v. tùy phiên bản); cảnh báo vẫn khác lỗi.
- `-Werror`: khiến compile thất bại khi có cảnh báo; chỉ bật khi dự án muốn chính sách nghiêm ngặt.
- `javac -version`: xem compiler nào đang chạy; `java -version`: xem runtime. Hai lệnh cần được kiểm tra nếu sử dụng nhiều JDK.

Có thể chạy riêng `javac -X` hoặc `javac --help` để xem các tùy chọn được JDK đang dùng hỗ trợ. Dùng `-Xmaxerrs` lớn hơn để khám phá những lỗi độc lập sau khi sửa lỗi cú pháp gốc, nhưng đừng dựa vào việc tăng số lượng diagnostic như một cách sửa lỗi.

**Kiểm tra trạng thái lệnh biên dịch:** Trong PowerShell, `$LASTEXITCODE` là exit code của lệnh `javac` vừa chạy; `0` biểu thị thành công. Trong bash, chạy `echo $?` ngay sau `javac` để xem exit code. Đừng chạy lệnh khác ở giữa rồi mới kiểm tra.

## 7. Phân biệt compile error, warning và lỗi khi chạy

| Giai đoạn | Dấu hiệu | Nên điều tra |
| --- | --- | --- |
| **Compile error** (`javac`) | `error:`, chương trình không biên dịch thành công | Cú pháp, kiểu, phân giải tên, access, dependency, cấu hình |
| **Warning** (`javac`) | `warning:`, compile có thể vẫn thành công | Hành vi dễ sai, API cũ, generic/raw type, `-Xlint` |
| **Runtime exception/error** (`java`) | `Exception in thread "main"`, stack trace hoặc thông báo launcher | Dữ liệu, điều kiện chạy, call stack, classpath runtime, logic |
| **Sai logic** | Chạy không lỗi nhưng in kết quả sai | Kiểm thử và phân tích thuật toán/dữ liệu, không chỉ đọc `javac` |

Ví dụ **biên dịch hợp lệ nhưng lỗi lúc chạy**:

```java
public class RuntimeDemo {
    public static void main(String[] args) {
        String message = null;
        System.out.println(message.length());
    }
}
```

Biên dịch với `javac -d out RuntimeDemo.java` rồi chạy `java -cp out RuntimeDemo` sẽ phát sinh `NullPointerException`; đây không phải chẩn đoán `javac`. Nội dung chi tiết của stack trace có thể khác giữa các bản JDK, nên không coi văn bản stack trace là output cố định. Lúc này sửa logic null và kiểm tra đầu vào, không tiếp tục thêm import.

Đừng hiểu câu `error: could not find or load main class` của **launcher `java`** là lỗi do parser `javac` phát hiện. Hãy xem tên đầy đủ lớp `main`, đường dẫn `-cp` và các file `.class` được sinh ra.

## 8. Sai lầm phổ biến khi sửa lỗi

- **Chỉ nhìn dấu `^`:** vị trí chỉ là nơi compiler nhận diện triệu chứng; luôn đọc cú pháp trước đó.
- **Sửa hàng loạt lỗi cùng lúc:** dễ đưa thêm lỗi và khó biết thay đổi nào giải quyết nguyên nhân. Ưu tiên thay đổi nhỏ, compile lại.
- **Viết sai tên do Java phân biệt chữ hoa-thường:** `total`, `Total`, `TOTAL` là ba tên khác nhau.
- **Thêm import không liên quan:** `cannot find symbol` cũng xảy ra khi typo tên biến cục bộ hoặc biến ngoài scope; import không thể tạo biến đó.
- **Sửa classpath thay cho lỗi cú pháp, hoặc ngược lại:** chẩn đoán về thư viện phải kiểm tra đúng dependency; diagnostic `';' expected` thường là cú pháp.
- **Quên tên file public class:** `public class SumDemo` phải nằm trong `SumDemo.java` (phân biệt chữ hoa-thường trên hệ thống tệp tương ứng).
- **Chạy file `.class` cũ sau compile thất bại:** chỉ chạy khi bước biên dịch hiện tại thực sự thành công.
- **Ẩn lỗi bằng cách xóa dòng:** chương trình compile được nhưng thiếu chức năng. Kiểm tra lại yêu cầu và output mong muốn.

## 9. Checklist thực hành

Khi có hàng loạt thông báo, hãy tự hỏi:

1. Lệnh `javac`, phiên bản JDK, package, tệp nguồn, đường dẫn nguồn và thư viện đã đúng chưa?
2. Diagnostic đầu tiên cho biết tệp, dòng, loại lỗi, tên nào và ngữ cảnh nào?
3. Có dấu ngoặc, dấu chấm phẩy, tên khai báo hoặc `import` sai ở dòng trước không?
4. Nhiều lỗi có cùng nhắc đến một kiểu/biến/phương thức bị thiếu không? Nếu có, đâu là lỗi khởi nguồn?
5. Có thể sửa **một nguyên nhân** rồi biên dịch lại để kiểm chứng không?
6. Sau khi hết compile error, chương trình đã chạy và cho output đúng chưa?

**Ghi nhớ:** `javac` báo nơi compiler không thể tiếp tục phân tích hoặc kiểm tra mã theo quy tắc Java; bạn cần lần về cấu trúc, khai báo hoặc cấu hình làm phát sinh lỗi đó. Sửa nguyên nhân gốc, biên dịch lại và xác minh bằng chạy thử đáng tin cậy hơn việc đếm số thông báo còn lại.
