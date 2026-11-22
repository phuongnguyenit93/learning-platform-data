# Biên dịch Java là gì và giải quyết vấn đề nào?

Một chương trình Java bắt đầu bằng mã nguồn mà lập trình viên có thể đọc và chỉnh sửa, chẳng hạn tệp `HelloCompilation.java`. Máy tính cần một cách biểu diễn có cấu trúc để thực thi chương trình đó. **Biên dịch Java (Java compilation)** là quá trình chuyển mã nguồn Java thành các tệp lớp (`.class`) chứa **bytecode**, đồng thời phát hiện nhiều lỗi cú pháp và kiểu dữ liệu trước khi chương trình chạy.

Điều quan trọng nhất cần phân biệt ngay từ đầu là **`javac` biên dịch mã nguồn; `java` khởi động môi trường thực thi chương trình**. Biên dịch thành công chưa có nghĩa chương trình đã chạy, cho kết quả đúng hoặc không thể gặp lỗi khi chạy.

## 1. Bức tranh tổng thể: từ tệp nguồn đến chương trình hoạt động

~~~text
Lập trình viên viết mã nguồn
        |
        v
HelloCompilation.java
        |
        | javac (trình biên dịch trong JDK)
        | - phân tích cú pháp, tên, kiểu và các quy tắc ngôn ngữ
        v
HelloCompilation.class  (bytecode + metadata của lớp)
        |
        | java HelloCompilation
        v
JVM: nạp lớp -> xác minh -> liên kết/khởi tạo khi cần
        |
        | thông dịch bytecode và/hoặc biên dịch JIT thành mã máy
        v
Chương trình chạy trên hệ điều hành và phần cứng
~~~

Sơ đồ trên là một mô hình để định hướng, không phải lời khẳng định rằng mọi giai đoạn đều diễn ra đúng một lần hay luôn theo cùng một thứ tự cố định. JVM có thể nạp lớp khi cần, còn JIT có thể chỉ biên dịch những đoạn mã được thực thi nhiều. Vì vậy, **biên dịch mã nguồn bằng `javac`** và **biên dịch JIT trong JVM** là hai công việc khác nhau.

Các thành phần cần nhận diện:

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| `.java` | Mã nguồn do người viết | `HelloCompilation.java` |
| `javac` | Trình biên dịch Java của JDK | `javac HelloCompilation.java` |
| `.class` | Tệp bytecode của một lớp hay kiểu được biên dịch | `HelloCompilation.class` |
| `java` | Lệnh khởi động ứng dụng Java | `java HelloCompilation` |
| JVM | Máy ảo thực thi bytecode, quản lý nạp lớp, bộ nhớ và các cơ chế runtime | JVM có trong Java runtime |
| JDK | Bộ phát triển gồm công cụ như `javac`, `java`, `javap` và runtime | JDK 17, JDK 21 |

Một tệp `.java` có thể tạo ra nhiều tệp `.class` nếu nó khai báo nhiều kiểu hoặc có lớp lồng nhau; hai phần mở rộng này không luôn tương ứng một-một.

## 2. Vì sao Java cần biên dịch?

**Thứ nhất, chuyển từ ngôn ngữ con người viết sang định dạng JVM hiểu được.** Câu lệnh `int total = price * quantity;` là mã nguồn Java. `javac` chuyển nó thành bytecode và thông tin về lớp, trường, phương thức, kiểu, hằng số... để JVM có thể nạp và thực thi theo đặc tả của Java.

**Thứ hai, phát hiện lỗi sớm.** Trình biên dịch kiểm tra cấu trúc chương trình, tên khai báo, tính phù hợp của kiểu, quyền truy cập và nhiều ràng buộc khác. Nếu gán chuỗi cho biến `int` mà không có phép chuyển đổi hợp lệ, quá trình biên dịch thất bại; không cần chạy tới câu lệnh ấy mới biết lỗi. Điều này giúp giảm chi phí sửa lỗi, nhưng **không chứng minh logic nghiệp vụ là đúng**.

**Thứ ba, tách mã nguồn khỏi môi trường phần cứng cụ thể.** `javac` thường tạo bytecode theo định dạng tệp lớp JVM, thay vì tạo trực tiếp mã máy x86 hay ARM cho mỗi hệ điều hành. Một bộ bytecode có thể chạy trên nhiều hệ thống có JVM tương thích, cùng phiên bản và đủ thư viện phụ thuộc. Đây là nền tảng của tính di động của Java, nhưng không có nghĩa mọi chương trình sẽ hoạt động giống hệt trên mọi máy: hệ điều hành, đường dẫn tệp, native library, charset mặc định, cấu hình hoặc phụ thuộc bên ngoài vẫn có thể khác nhau.

**Thứ tư, tạo đầu ra để đóng gói và phân phối.** Các tệp `.class` thường được đưa vào `.jar` hoặc cấu trúc triển khai của ứng dụng. Người chạy có thể dùng đầu ra đã biên dịch mà không cần nhận toàn bộ mã nguồn. Việc đóng gói JAR là bước khác với biên dịch; một JAR chứa các lớp cũng cần entry point và dependencies phù hợp mới chạy được.

**Thứ năm, để runtime tự tối ưu theo tình huống chạy thật.** Bytecode giữ một dạng trung gian phù hợp để JVM thực thi bằng các kỹ thuật như thông dịch và biên dịch JIT. Khả năng tối ưu này không biến mọi chương trình Java thành nhanh hơn mặc định; kết quả còn phụ thuộc thuật toán, dữ liệu, JVM, việc khởi động và tài nguyên máy.

### Biên dịch giải quyết được gì, và không giải quyết được gì?

| Vấn đề | `javac` có hỗ trợ? | Giới hạn |
| --- | --- | --- |
| Cú pháp sai, kiểu không tương thích, tên không tìm thấy | Có, thường báo lỗi khi biên dịch | Chẩn đoán phụ thuộc ngữ cảnh và phiên bản công cụ |
| Chuyển mã Java thành bytecode | Có | Đầu ra vẫn cần runtime tương thích |
| Phát hiện phép tính đúng cú pháp nhưng sai ý định | Không bảo đảm | Cần test, review và kiểm chứng nghiệp vụ |
| Phát hiện mọi lỗi như chia cho 0 với dữ liệu thực tế | Không | Có lỗi chỉ xảy ra lúc chạy |
| Bảo đảm không thiếu cấu hình, thư viện hay lỗi môi trường | Không | Cần kiểm tra đóng gói và runtime |
| Biên dịch bytecode thành mã máy trong lúc chạy | Không phải trách nhiệm chính của `javac` | JVM có thể làm thông qua JIT |

## 3. Ví dụ đầu tiên: biên dịch khác chạy như thế nào?

Cài JDK 17 trở lên và kiểm tra hai công cụ:

~~~sh
javac -version
java -version
~~~

Phiên bản hiển thị phụ thuộc JDK được cài đặt. Tạo một tệp **`HelloCompilation.java`** có nội dung hoàn chỉnh sau (tên tệp khớp tên lớp `public`):

~~~java
public class HelloCompilation {
    public static void main(String[] args) {
        int price = 120;
        int quantity = 3;
        int total = price * quantity;

        System.out.println("Tổng: " + total);
    }
}
~~~

Mở terminal tại thư mục chứa tệp và chạy lần lượt:

~~~sh
javac -encoding UTF-8 HelloCompilation.java
java HelloCompilation
~~~

Đầu ra của lệnh `java` là:

~~~text
Tổng: 360
~~~

Quan sát ba mốc khác nhau:

1. **Trước `javac`:** Có mã nguồn `HelloCompilation.java`; chưa có tệp lớp mới từ ví dụ này.
2. **Sau `javac` thành công:** Có `HelloCompilation.class`. Trình biên dịch thông thường không thực hiện phương thức `main` và không in dòng `Tổng: 360`.
3. **Sau `java HelloCompilation`:** JVM tải lớp, gọi `public static void main(String[] args)` và chương trình in kết quả ra console.

Ở đây `java` nhận **tên lớp có `main`**, không nhận đường dẫn `HelloCompilation.class`. Khi chạy từ thư mục hiện tại, classpath mặc định thường chứa thư mục hiện tại; để minh bạch và tránh phụ thuộc cấu hình, có thể dùng:

~~~sh
java -cp . HelloCompilation
~~~

Trong lệnh này, `-cp .` chỉ định thư mục hiện tại là classpath. Nếu có lỗi biên dịch, **đừng tiếp tục chạy một `.class` cũ** rồi tưởng đó là kết quả của mã nguồn vừa sửa: tệp lớp được sinh ở lần biên dịch thành công trước có thể vẫn còn.

### Thử thay đổi một dòng

Đổi `quantity = 3` thành `quantity = 4` trong mã nguồn. Nếu chỉ chạy lại `java HelloCompilation` mà không biên dịch, kết quả vẫn có thể là `360` vì JVM đang đọc `.class` cũ. Sau khi chạy lại `javac -encoding UTF-8 HelloCompilation.java`, kết quả mới là `Tổng: 480`. Đây là minh chứng trực tiếp rằng lưu tệp nguồn và biên dịch là hai hành động khác nhau.

## 4. Trình biên dịch kiểm tra những gì?

Một cách nhìn dễ hiểu về công việc của `javac`:

1. **Đọc và phân tích cú pháp:** Từ các ký tự, từ khóa, dấu ngoặc, toán tử, chú thích... tạo ra cấu trúc cú pháp của chương trình. Thiếu `}` hoặc viết một câu lệnh sai ngữ pháp có thể dừng tại đây.
2. **Phân giải tên và ngữ cảnh:** Liên kết tên biến, phương thức, lớp, package và import với khai báo tương ứng; kiểm tra phạm vi nhìn thấy và quyền truy cập.
3. **Kiểm tra kiểu và quy tắc ngôn ngữ:** Đánh giá xem các biểu thức, phép gán, lời gọi phương thức, xử lý ngoại lệ được kiểm tra và nhiều quy tắc khác có hợp lệ không.
4. **Tạo bytecode và metadata:** Sinh chỉ dẫn JVM, bảng hằng số, chữ ký, thông tin lớp, thuộc tính... rồi ghi ra tệp lớp.

Đây là các nhóm trách nhiệm để học, không phải cam kết mô tả chính xác tất cả pass nội bộ của mọi bản `javac`.

Ví dụ một lỗi kiểu, lưu riêng thành **`BrokenType.java`**:

~~~java
public class BrokenType {
    public static void main(String[] args) {
        int count = "3";
        System.out.println(count);
    }
}
~~~

Chạy:

~~~sh
javac BrokenType.java
~~~

`javac` báo lỗi vì chuỗi ký tự `"3"` có kiểu `String` và không thể gán trực tiếp cho `int`. Cụm từ và vị trí trong thông báo lỗi có thể thay đổi theo phiên bản JDK, nên không nên kiểm thử bằng cách so khớp từng ký tự của lời báo lỗi.

Nếu ý định là chuyển chuỗi chữ số thành số nguyên, có thể dùng `Integer.parseInt("3")`. Lệnh này **hợp lệ khi biên dịch**, nhưng có thể gây `NumberFormatException` lúc chạy nếu chuỗi nhập không phải số nguyên hợp lệ. Đó là ví dụ điển hình cho ranh giới giữa kiểm tra tĩnh và điều kiện runtime.

### Lỗi biên dịch, lỗi lúc chạy và lỗi logic

| Loại vấn đề | Ví dụ | Khi nào thấy? | Cách xử lý |
| --- | --- | --- | --- |
| Cú pháp/kiểu | Thiếu dấu `;`; gán `String` cho `int` | `javac` báo lỗi | Sửa mã theo cú pháp và kiểu hợp lệ |
| Khi chạy (runtime) | Chia cho 0 với số nguyên; thiếu tệp dữ liệu | Khi đường chạy tương ứng được thực thi | Xử lý đầu vào, exception và trạng thái môi trường |
| Logic | Nhân sai đơn giá, dùng sai công thức chiết khấu | Chương trình vẫn có thể biên dịch và chạy | Kiểm thử theo yêu cầu nghiệp vụ |

Một ví dụ lỗi runtime độc lập, lưu thành **`RuntimeFailure.java`**:

~~~java
public class RuntimeFailure {
    public static void main(String[] args) {
        int divisor = 0;
        int result = 10 / divisor;
        System.out.println(result);
    }
}
~~~

~~~sh
javac RuntimeFailure.java
java RuntimeFailure
~~~

Biên dịch thành công; lúc chạy phép chia số nguyên cho 0 gây `ArithmeticException`. Stack trace và số dòng cụ thể phụ thuộc tệp cùng JDK nên không cố định ở đây. Sự khác biệt này rất quan trọng: **`javac` không chạy mọi nhánh của chương trình để chứng minh các điều kiện runtime đều an toàn**.

## 5. Bytecode là gì và tại sao không phải mã máy?

Bytecode trong tệp `.class` là tập lệnh và cấu trúc dữ liệu được định nghĩa cho JVM. Nó có các thao tác ở mức máy ảo, ví dụ nạp giá trị, thực hiện phép toán, gọi phương thức và trả về kết quả. CPU của máy tính không mặc nhiên chạy trực tiếp tệp `.class` như một chương trình native. JVM phải đọc, kiểm tra và thực thi nó theo cách thích hợp.

Có thể khảo sát đầu ra từ ví dụ đầu bằng:

~~~sh
javap -c HelloCompilation
~~~

`javap` là công cụ phân tích tệp lớp của JDK; tùy tùy chọn, nó hiển thị chữ ký phương thức hoặc các chỉ dẫn bytecode. Dòng mã nguồn như `int total = price * quantity;` có thể tương ứng nhiều chỉ dẫn. Không cần ghi nhớ opcode ở bài mở đầu; hãy nhận biết **một chương trình nguồn được biểu diễn lại dưới dạng khác**.

Tệp `.class` còn chứa phiên bản định dạng lớp. Ví dụ, định dạng của Java 17 có major version 61; Java 21 có major version 65. JVM quá cũ có thể từ chối tệp lớp mới với `UnsupportedClassVersionError`. Đây là vấn đề tương thích bytecode, khác với việc tìm không thấy lớp trên classpath.

### `javac` và JIT không phải cùng một bước

- **`javac`:** Chạy trước khi khởi động ứng dụng theo cách thông thường; biên dịch từ `.java` sang bytecode `.class`.
- **Thông dịch trong JVM:** Thực thi ý nghĩa của bytecode trong runtime.
- **JIT (just-in-time compilation):** Một cơ chế runtime có thể biên dịch những đoạn bytecode phù hợp thành mã máy tối ưu dựa trên quan sát khi chạy; tùy JVM và cấu hình, cách triển khai có thể khác.

Việc một JVM có JIT không đồng nghĩa mọi phương thức đều chắc chắn được JIT biên dịch, hay JIT đã xảy ra ngay sau `javac`. Từ “biên dịch” xuất hiện ở cả hai nơi, nhưng **đầu vào, đầu ra và thời điểm** khác nhau.

## 6. Bài toán nhiều lớp và package

Khi dự án có package, tên lớp dùng lúc chạy là **tên đầy đủ gồm package**, còn classpath trỏ tới **gốc của cấu trúc package**. Ví dụ tạo cây tệp:

~~~text
project/
└── src/
    └── demo/
        ├── Calculator.java
        └── App.java
~~~

Nội dung **`src/demo/Calculator.java`**:

~~~java
package demo;

public final class Calculator {
    private Calculator() {
    }

    public static int twice(int value) {
        return value * 2;
    }
}
~~~

Nội dung **`src/demo/App.java`**:

~~~java
package demo;

public class App {
    public static void main(String[] args) {
        System.out.println("Kết quả: " + Calculator.twice(7));
    }
}
~~~

Tại thư mục `project`, tạo thư mục đầu ra `out` nếu chưa có, rồi biên dịch cả hai tệp:

~~~sh
mkdir out
javac -encoding UTF-8 -d out src/demo/Calculator.java src/demo/App.java
java -cp out demo.App
~~~

Lệnh `mkdir out` chỉ cần thực hiện một lần khi `out` chưa tồn tại. Trên Windows PowerShell và các shell thông dụng có lệnh tương đương; nếu thư mục đã tồn tại thì bỏ qua bước tạo. Đầu ra:

~~~text
Kết quả: 14
~~~

Kết quả biên dịch có cấu trúc chính:

~~~text
out/
└── demo/
    ├── Calculator.class
    └── App.class
~~~

Ở đây:

- `package demo;` xác định tên package. Thông lệ đặt tệp nguồn trong đường dẫn tương ứng để dễ quản lý.
- `-d out` chỉ thư mục gốc của đầu ra; `javac` tạo các thư mục con phù hợp với package bên trong nó.
- `-cp out` cho JVM biết nơi tìm lớp. Nó không chỉ tới riêng `out/demo` vì tên đầy đủ `demo.App` đã bao gồm package.
- `java -cp out demo.App` chạy `main` của lớp `demo.App`, không chạy `App` như lớp ở default package.
- Biên dịch cần tìm được các lớp, kiểu và thư viện mà mã nguồn phụ thuộc. **Classpath tại thời điểm biên dịch** và **classpath lúc chạy** đều quan trọng; thiếu dependencies ở một trong hai thời điểm gây các lỗi khác nhau.

Dự án thật thường không yêu cầu gõ tay từng tệp `.java`: các công cụ như Maven/Gradle xác định source set, dependencies và gọi trình biên dịch theo cấu hình build. Tuy vậy, hiểu lệnh `javac` trực tiếp giúp phân biệt rõ vấn đề thuộc mã nguồn, biên dịch, đóng gói hay runtime.

## 7. Quy trình thực tế khi biên dịch

Một vòng làm việc thông thường là:

~~~text
Viết/sửa .java
      |
      v
Chạy build / javac ---- lỗi biên dịch? ----> sửa mã nguồn rồi biên dịch lại
      |
      | thành công
      v
.class / thư viện / artifact
      |
      v
Chạy ứng dụng và kiểm thử ---- lỗi runtime / logic? ----> sửa + biên dịch + thử lại
      |
      v
Đóng gói, phân phối và vận hành
~~~

Một số điểm kỹ thuật thường gây nhầm:

**Phiên bản nguồn và runtime.** Với JDK hỗ trợ tùy chọn này, `javac --release 17 HelloCompilation.java` yêu cầu biên dịch theo mức ngôn ngữ, bytecode và API chuẩn của Java 17. Ví dụ khi đang dùng JDK 21, tùy chọn này hữu ích để xuất mã cho mục tiêu Java 17 nếu chương trình và phụ thuộc tương thích. Dùng riêng `-source 17 -target 17` không bảo đảm đã giới hạn toàn bộ Java API đúng phiên bản mục tiêu. Kiểm tra JDK chạy chương trình bằng `java -version`.

**Classpath.** Tệp lớp đúng vẫn có thể không chạy được nếu `java` đang tìm sai nơi hoặc thiếu JAR phụ thuộc. Khi thấy `ClassNotFoundException` hay `NoClassDefFoundError`, cần kiểm tra tên lớp đầy đủ, thư mục gốc, JAR và dependency graph; hai lỗi này có thể có nguyên nhân khác nhau.

**Tên tệp và lớp `public`.** Một lớp cấp cao nhất `public class Example` phải nằm trong `Example.java` (với các quy tắc tên tệp của Java). Đổi tên tệp tùy tiện có thể làm biên dịch lỗi. Chữ hoa và chữ thường trong tên lớp phải được giữ nhất quán.

**Thứ tự thao tác.** Lưu mã nguồn, chạy `javac`, rồi chạy `java`. Khi build lỗi, hãy đọc lỗi biên dịch đầu tiên có ý nghĩa trước khi chạy đầu ra cũ. Dọn sản phẩm build cũ khi cần kiểm tra một bản mới thực sự được tạo.

**Encoding.** Với nội dung có tiếng Việt, `-encoding UTF-8` giúp `javac` đọc tệp nguồn đúng khi tệp được lưu UTF-8. Encoding của terminal khi *hiển thị* stdout là vấn đề riêng; nếu console hiển thị chữ bị lỗi, hãy kiểm tra terminal và runtime encoding thay vì lập tức kết luận `javac` đã tạo bytecode sai.

**Compile một lớp và compile toàn dự án.** Trình biên dịch có thể tìm và biên dịch thêm mã nguồn phụ thuộc theo sourcepath/classpath và cấu hình; không nên phụ thuộc tình cờ vào hành vi tìm nguồn mặc định để build một dự án lớn. Với dự án nhiều module, hãy dùng cấu hình build xác định rõ nguồn và phụ thuộc.

**Chạy trực tiếp tệp nguồn.** Từ Java 11, lệnh như `java HelloCompilation.java` có chế độ chạy chương trình nguồn đơn tệp: launcher xử lý biên dịch trong bộ nhớ rồi chạy, thường không để lại `HelloCompilation.class` trên đĩa theo cách gọi này. Tính năng tiện lợi ấy **không làm mất đi bước chuyển từ mã nguồn sang dạng thực thi**, cũng không biến `java File.java` thành cách thay thế mọi build nhiều tệp của dự án.

## 8. Những hiểu lầm cần tránh

| Nhận định | Giải thích chính xác hơn |
| --- | --- |
| “Biên dịch Java ra mã máy chạy ngay trên CPU.” | `javac` thông thường tạo bytecode cho JVM, không tạo executable native cho CPU. |
| “Biên dịch thành công là chương trình đúng.” | Chỉ xác nhận mã đáp ứng các kiểm tra tĩnh mà trình biên dịch thực hiện trong cấu hình ấy. |
| “`javac` và `java` là cùng một lệnh.” | `javac` biên dịch; `java` khởi động chương trình. Chế độ chạy tệp nguồn là một trường hợp đặc biệt của launcher. |
| “Một tệp Java chắc chắn sinh đúng một tệp lớp.” | Một nguồn có thể tạo nhiều `.class`. |
| “Cứ có JVM là chạy được mọi `.class`.” | Phiên bản bytecode, thư viện, cấu hình và môi trường phải tương thích. |
| “JIT xảy ra khi chạy `javac`.” | JIT là một kỹ thuật bên trong JVM khi chương trình chạy. |
| “`import` tự tải về thư viện.” | `import` cho phép dùng tên khai báo theo quy tắc Java; dependency phải thực sự có trong cấu hình biên dịch/runtime. |

## 9. Thực hành và tự kiểm tra hiểu biết

**Bài tập 1 — Phân biệt hai thời điểm.** Chạy lại ví dụ `HelloCompilation`, sửa `quantity` rồi chạy `java HelloCompilation` *trước* khi chạy lại `javac`. Giải thích vì sao bạn có thể thấy kết quả cũ. Sau đó biên dịch lại và xác nhận thay đổi.

**Bài tập 2 — Sửa lỗi biên dịch.** Với `BrokenType.java`, thay `int count = "3";` bằng `int count = Integer.parseInt("3");`. Sau khi biên dịch và chạy thành công, hãy thử `Integer.parseInt("three")`: điều gì thay đổi giữa lỗi biên dịch và lỗi lúc chạy? Không cần ép chương trình bắt exception ở bài này; mục đích là nhận diện giai đoạn phát hiện.

**Bài tập 3 — Nhận diện classpath.** Với project package `demo`, dự đoán kết quả khi chạy `java App` thay vì `java -cp out demo.App` từ thư mục `project`. Vì sao JVM không tìm thấy lớp yêu cầu theo tên/đường dẫn đó?

**Bài tập 4 — Giải thích bytecode.** Sau khi dùng `javap -c HelloCompilation`, trình bày một câu về `.java`, một câu về `.class` và một câu về vai trò của JVM. Không cần học thuộc mã lệnh JVM.

Để tự đánh giá, bạn nên trả lời được năm câu hỏi:

1. **Biên dịch Java nhận đầu vào và cho đầu ra gì?** Mã nguồn `.java` → bytecode cùng metadata trong `.class` (theo cách dùng `javac` thông thường).
2. **Vì sao lỗi kiểu có thể xuất hiện trước khi chạy?** Vì trình biên dịch kiểm tra ràng buộc kiểu trên mã nguồn mà không cần thực thi phương thức `main`.
3. **Khi nào nhìn thấy `System.out.println`?** Khi JVM thực thi dòng lệnh đó, không phải lúc `javac` sinh tệp lớp.
4. **Tại sao có `.class` vẫn có thể chạy lỗi?** Vì còn yêu cầu runtime: JVM tương thích, tìm được lớp/dependencies, cấu hình hợp lệ và đường thực thi an toàn.
5. **JIT nằm ở đâu?** Trong quá trình thực thi của JVM (nếu JVM sử dụng cơ chế này), khác với bước `javac` trước khi chạy.

**Kết nối sang phần học kế tiếp:** Khi đã nắm `.java → javac → .class → JVM`, có thể học sâu lần lượt cú pháp và type checking, cấu trúc classfile/bytecode, classpath và module path, class loading/linking, JIT, và công cụ build. Mỗi phần giải quyết một câu hỏi riêng; bài này cung cấp bản đồ để không nhầm chúng là một bước duy nhất.