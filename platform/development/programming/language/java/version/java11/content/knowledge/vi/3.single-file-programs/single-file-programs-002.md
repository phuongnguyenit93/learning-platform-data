# Tổ chức lớp, main và helper trong một tệp Java (Java 11+)

## Mục tiêu và phạm vi

Một chương trình Java nhỏ có thể được viết trong **một tệp nguồn `.java`** mà vẫn có cấu trúc rõ ràng: lớp chính chịu trách nhiệm khởi động, phương thức `main` điều phối luồng chạy, còn các *helper* thực hiện những thao tác nhỏ và có tên dễ hiểu. Một tệp nguồn **không đồng nghĩa** với chỉ một lớp: tệp có thể chứa nhiều phương thức, lớp lồng nhau và nhiều lớp cấp cao nhất (*top-level classes*) theo các quy tắc của Java.

Bài này dùng cú pháp chuẩn **tương thích Java 11** và vẫn hoạt động trên các JDK hiện đại. Java 11 đã có chế độ chạy trực tiếp tệp `.java` bằng lệnh `java File.java`; khả năng đó vẫn được hỗ trợ. Các bản JDK mới hơn đã mở rộng cách khởi chạy mã nguồn, nhưng những ví dụ ở đây cố ý dùng cấu trúc `class` và `public static void main(String[] args)` để người học có thể biên dịch và chạy trên Java 11.

Sau bài học, bạn có thể:

1. Chọn đúng vị trí cho `main`, helper method, helper class và import.
2. Viết một tệp `.java` chứa một lớp `public` và các lớp helper không `public`.
3. Phân biệt helper method `static`, lớp helper top-level và lớp helper lồng `static`.
4. Chạy bằng cả `java File.java` và cặp lệnh `javac File.java` / `java MainClass`.
5. Tránh lỗi tên tệp, phạm vi truy cập, gọi phương thức `static` và chọn sai lớp khi khởi chạy.

## 1. Vai trò của tệp, lớp, main và helper

Hình dung trách nhiệm theo ba tầng:

~~~text
ScoreReport.java              <- tệp mã nguồn / compilation unit
├── public class ScoreReport  <- điểm vào chương trình
│   └── main(String[] args)   <- nhận đầu vào, gọi nghiệp vụ, in kết quả
└── final class ScoreMath     <- helper top-level cùng tệp, không public
    ├── sum(...)
    ├── average(...)
    └── countAtLeast(...)
~~~

- **Tệp nguồn:** thường có cấu trúc `package` (nếu dùng), rồi các lệnh `import`, tiếp theo các khai báo lớp/interface/kiểu cấp cao nhất. Một `.java` có thể khai báo nhiều loại top-level.
- **Lớp chính:** đặt tên mô tả mục đích của chương trình, ví dụ `ScoreReport`. Với cách tổ chức truyền thống, lớp này thường là lớp `public` duy nhất của tệp.
- **`main`:** trong phong cách Java 11, điểm vào thông dụng là `public static void main(String[] args)`; JVM gọi phương thức này để bắt đầu chương trình. `args` chứa các đối số dòng lệnh ở dạng `String`.
- **Helper method:** một phương thức làm một việc nhỏ và rõ ràng, ví dụ `formatTitle` hoặc `calculateTotal`. Helper chỉ dùng bên trong lớp nên ưu tiên `private`.
- **Helper class:** một kiểu chứa nhiều phương thức hoặc dữ liệu liên quan. Có thể đặt ở **cấp top-level trong cùng tệp** hoặc **lồng bên trong lớp chính**.
- **`static`:** thành viên thuộc về lớp, có thể được gọi từ `static main` mà không tạo đối tượng. Helper cần trạng thái riêng theo từng đối tượng thì nên là phương thức instance và được gọi trên một instance thích hợp.

**Nguyên tắc tổ chức:** `main` nên dễ đọc như một danh sách các bước; phép tính, chuyển đổi, xác thực hoặc định dạng cụ thể được đặt vào helper. Cấu trúc rõ ràng quan trọng hơn việc cố dùng nhiều lớp cho một bài rất nhỏ.

## 2. Mẫu đơn giản nhất: một class với helper method private static

Tạo tệp **`GreetingApp.java`**:

~~~java
public class GreetingApp {
    public static void main(String[] args) {
        String target = args.length == 0 ? "Java" : args[0];
        System.out.println(makeGreeting(target));
    }

    private static String makeGreeting(String target) {
        return "Hello, " + target + "!";
    }
}
~~~

Chạy trực tiếp từ JDK 11 trở lên:

~~~bash
java GreetingApp.java Mai
~~~

**Stdout:**

~~~text
Hello, Mai!
~~~

Hoặc biên dịch rồi chạy:

~~~bash
javac GreetingApp.java
java GreetingApp Mai
~~~

Kết quả stdout giống hệt.

Điều cần chú ý:

- `GreetingApp` là lớp `public` và tên tệp là `GreetingApp.java`.
- `main` là điểm vào, lấy `args[0]` nếu có; nếu không có đối số thì dùng `"Java"`.
- `makeGreeting` có `private` vì chỉ lớp này dùng; có `static` nên `main` gọi trực tiếp được.
- `makeGreeting` trả về chuỗi thay vì tự in ra console, giúp tách **xử lý dữ liệu** khỏi **xuất kết quả**.
- `main` không cần `new GreetingApp()` vì cả `main` và helper đều `static`.
- Với chương trình chỉ có một vài helper liên quan chặt đến lớp chính, đây là cấu trúc dễ duy trì nhất.

Phần mã trên là một chương trình hoàn chỉnh, không cần thêm class hoặc thư viện ngoài Java SE.

## 3. Một tệp chứa nhiều lớp top-level: main class + helper class

Khi có nhiều helper cùng giải quyết một trách nhiệm (ví dụ phép toán trên điểm số), gom chúng vào một lớp riêng giúp `main` gọn và phân biệt giao diện điều khiển với logic xử lý. Vẫn chỉ cần một tệp `.java`.

Tạo tệp **`ScoreReport.java`** với **toàn bộ** mã sau:

~~~java
import java.util.Locale;

public class ScoreReport {
    public static void main(String[] args) {
        // main nhận tham số và điều phối, không chứa thuật toán thống kê.
        int minimum = args.length == 0 ? 7 : Integer.parseInt(args[0]);
        int[] scores = {8, 10, 6};

        System.out.println("total=" + ScoreMath.sum(scores));
        System.out.printf(
                Locale.ROOT,
                "average=%.2f%n",
                ScoreMath.average(scores)
        );
        System.out.println(
                "atLeast" + minimum + "="
                        + ScoreMath.countAtLeast(scores, minimum)
        );
    }
}

// Lớp thứ hai cùng tệp: package-private, không khai báo public.
final class ScoreMath {
    private ScoreMath() {
        // Utility class không cần tạo instance.
    }

    static int sum(int[] values) {
        int result = 0;
        for (int value : values) {
            result = Math.addExact(result, value);
        }
        return result;
    }

    static double average(int[] values) {
        if (values.length == 0) {
            throw new IllegalArgumentException(
                    "values must not be empty"
            );
        }
        return (double) sum(values) / values.length;
    }

    static int countAtLeast(int[] values, int minimum) {
        int count = 0;
        for (int value : values) {
            if (value >= minimum) {
                count++;
            }
        }
        return count;
    }
}
~~~

### Cách chạy thứ nhất: Java source-file mode

~~~bash
java ScoreReport.java
~~~

**Stdout chính xác** với dữ liệu mặc định:

~~~text
total=24
average=8.00
atLeast7=2
~~~

Thử truyền đối số cho chương trình:

~~~bash
java ScoreReport.java 9
~~~

**Stdout:**

~~~text
total=24
average=8.00
atLeast9=1
~~~

### Cách chạy thứ hai: biên dịch tường minh

~~~bash
javac ScoreReport.java
java ScoreReport
~~~

Kết quả không truyền đối số là ba dòng `total=24`, `average=8.00`, `atLeast7=2` như ở trên. Trong ví dụ không có `package`, lệnh `javac` thường sinh ra hai file mã máy Java: `ScoreReport.class` và `ScoreMath.class`. Một tệp nguồn chứa **hai lớp** có thể tạo **hai tệp `.class`**.

Muốn chạy bản đã biên dịch với tham số:

~~~bash
java ScoreReport 9
~~~

Hai cách gọi `java ScoreReport.java 9` và `java ScoreReport 9` đều chuyển chuỗi `"9"` tới `main`, nhưng **cách chọn và nạp chương trình khác nhau**; xem bảng so sánh ở mục 5.

### Phân tích thiết kế

- **`ScoreReport`** chứa `main` và phần hiển thị. Lớp chính là top-level `public` duy nhất, đồng thời được khai báo **trước `ScoreMath`** để phù hợp quy tắc chọn lớp khi chạy source-file mode.
- **`ScoreMath`** là lớp top-level thứ hai; bỏ từ khóa `public` nghĩa là *package-private* (chỉ có quyền truy cập trong package), không phải `private`. Từ khóa `final` chỉ ngăn kế thừa lớp này.
- **Constructor `private ScoreMath()`** ngăn tạo đối tượng của utility class từ bên ngoài chính lớp đó. Các phương thức xử lý là `static`, vì vậy gọi bằng tên lớp `ScoreMath.sum(...)`.
- `sum` dùng `Math.addExact` để không âm thầm bỏ qua lỗi tràn số nguyên; `average` kiểm tra mảng rỗng trước khi chia; `countAtLeast` xử lý ngưỡng đầu vào. Những helper này **không in ra console**, giúp tái sử dụng và kiểm thử độc lập.
- `Locale.ROOT` trong `printf` giúp dấu thập phân luôn là dấu chấm trong ví dụ, không lệ thuộc locale của máy.
- `Integer.parseInt(args[0])` biến chuỗi thành số. Đầu vào không phải số hợp lệ sẽ ném `NumberFormatException`; ứng dụng thực tế nên xác thực số lượng/định dạng đối số và đưa ra thông báo dễ hiểu.
- `main` là nơi điều phối thao tác nhận đối số, gọi helper và hiển thị; loại logic tính toán đã được đóng gói thành những phương thức có tên diễn đạt chức năng.

**Vì sao cần một lớp helper, thay vì ba helper method đặt ngay trong `ScoreReport`?** Vì `ScoreMath` tập trung các phép toán có thể được dùng lại độc lập với giao diện dòng lệnh. Nếu chỉ có một phép tính nhỏ dùng đúng một lần, chuyển nó thành một lớp mới có thể làm chương trình rườm rà hơn.

## 4. Một lựa chọn khác: lớp helper lồng static bên trong lớp chính

Đôi khi helper chỉ phục vụ một chương trình và không nên hiện thành một kiểu top-level mà các lớp khác trong cùng package có thể thấy. Dùng **`private static class`** hoặc **`private static final class`** lồng trong lớp chính.

Tạo tệp **`NestedHelperDemo.java`**:

~~~java
import java.util.Locale;

public class NestedHelperDemo {
    public static void main(String[] args) {
        System.out.println(TextHelper.normalize("  JAVA  "));
    }

    private static final class TextHelper {
        private TextHelper() {
        }

        static String normalize(String value) {
            return value.strip().toLowerCase(Locale.ROOT);
        }
    }
}
~~~

Chạy:

~~~bash
java NestedHelperDemo.java
~~~

**Stdout:**

~~~text
java
~~~

Đây cũng là một tệp chương trình hoàn chỉnh và dùng `String.strip()` (có từ Java 11).

Khác biệt giữa các kiểu helper:

| Cách đặt helper | Quyền truy cập điển hình | Khi nào phù hợp |
| --- | --- | --- |
| `private static` **method** trong lớp chính | Chỉ từ lớp chứa phương thức | Một bước xử lý nhỏ, ít chức năng liên quan |
| **Top-level class** không `public` trong cùng tệp | Các kiểu khác trong cùng package có thể truy cập nếu thành viên cho phép | Có một nhóm thuật toán hoặc một kiểu dữ liệu độc lập, nhưng chưa cần tệp riêng |
| `private static class` **lồng** trong lớp chính | Chỉ dùng trong phạm vi lớp chứa (kể cả thành viên lồng có quyền truy cập phù hợp) | Nhóm helper gắn chặt với một lớp và muốn giấu chi tiết đó khỏi package |
| Phương thức **instance** trên một object | Theo quyền truy cập và đối tượng được tạo | Cần lưu và sử dụng trạng thái của từng object, không chỉ tính toán tĩnh |

**Lưu ý thuật ngữ:** `TextHelper` là *nested class*, không phải lớp top-level thứ hai. `static` ở đây nghĩa là lớp lồng **không cần instance của `NestedHelperDemo`** để tạo/dùng; nó không phải là cách khai báo được phép đối với một lớp top-level. Ngược lại, một **inner class** không `static` gắn với một object của lớp bao ngoài, nên không phải lựa chọn mặc định cho các utility helper độc lập.

## 5. Chạy trực tiếp mã nguồn khác gì biên dịch bằng javac?

Từ Java 11, bạn có thể chạy trực tiếp một tệp nguồn với `java File.java` (JEP 330). Đây vẫn là công cụ hữu ích cho bài học, thử nghiệm nhỏ hoặc tiện ích có phạm vi gọn. Cách biên dịch bằng `javac` cũng vẫn được dùng trong các dự án có build và kiểm thử.

| Thao tác | Chạy trực tiếp `java ScoreReport.java` | `javac ScoreReport.java` rồi `java ScoreReport` |
| --- | --- | --- |
| Đầu vào cho launcher | Đường dẫn **tệp mã nguồn** `.java` | **Tên lớp** đã biên dịch (binary class name) |
| Biên dịch | Launcher biên dịch mã nguồn phù hợp trước khi chạy | Lệnh `javac` thực hiện bước biên dịch riêng |
| `.class` sinh ở thư mục làm việc | Thông thường không tạo tệp `.class` cạnh nguồn do launcher biên dịch vào bộ nhớ | Với ví dụ không `package`, tạo `ScoreReport.class` và `ScoreMath.class` |
| Chọn lớp khởi động | Với mã nguồn thông thường, chọn **lớp top-level đầu tiên** trong tệp | Chọn **lớp có tên được chỉ ra** trong lệnh `java` |
| Sửa mã nguồn rồi chạy lại | Gọi `java File.java` là launcher biên dịch lại từ nguồn | Phải `javac` lại để cập nhật bytecode trước khi `java ClassName` |
| Tình huống dùng | Chương trình nhỏ, kiểm tra nhanh, ví dụ học tập | Build tách bước rõ ràng, kiểm thử, đóng gói, triển khai |

**Thứ tự khai báo là quan trọng trong source-file mode.** Với các ví dụ dùng cú pháp Java 11, nên đặt lớp có `main` lên trước các lớp helper top-level. Khi chạy `java ScoreReport.java`, launcher chọn lớp top-level đầu tiên; nếu bạn đặt `ScoreMath` lên trước mà lớp này không có `main`, có thể nhận lỗi khởi động. Trong khi đó, `java ScoreReport` sau khi biên dịch chọn lớp theo **tên** và không phụ thuộc thứ tự khai báo top-level trong tệp nguồn.

**Phân biệt phạm vi theo phiên bản:** Ở Java 11, chế độ chạy mã nguồn trực tiếp tập trung vào một tệp và không tự tìm thêm tệp `.java` khác để biên dịch. Từ JDK 22, launcher có thêm hỗ trợ chương trình gồm **nhiều tệp nguồn** khi cấu trúc nguồn/package đáp ứng quy tắc (JEP 458). Do đó, không nên phát biểu chung rằng mọi phiên bản Java hiện đại chỉ chạy được đúng một source file. Bài này chỉ yêu cầu **tổ chức nhiều class/helper trong chính một tệp** và cách làm đó tương thích cả Java 11 lẫn các bản mới.

**Cú pháp `main`:** `public static void main(String[] args)` vẫn chạy trên JDK hiện đại; các bản JDK mới có thêm lựa chọn cú pháp rút gọn, nhưng chúng không tự động áp dụng cho mã nguồn cần tương thích Java 11.

Nếu biên dịch trên JDK mới và cần bảo đảm code còn dùng API/cú pháp Java 11, có thể dùng (khi phiên bản `javac` đang chạy vẫn hỗ trợ mức release 11):

~~~bash
javac --release 11 ScoreReport.java
java ScoreReport
~~~

Lệnh `--release 11` kiểm tra cú pháp và API mục tiêu khi biên dịch; để xác nhận tương thích khi triển khai, hãy chạy thử trên JVM thực tế được yêu cầu. Không cần dùng `--enable-preview` cho các ví dụ trong bài.

## 6. Những quy tắc cấu trúc file cần ghi nhớ

### 6.1. Vị trí package, import và lớp

Với một tệp nguồn Java thông thường, cấu trúc tổng quát là:

~~~java
package example;                // Nếu có package, khai báo trước import.
import java.util.Locale;       // Import đứng trước khai báo top-level.

public class MainApp {
    public static void main(String[] args) {
        System.out.println(Helper.label("java"));
    }
}

final class Helper {
    private Helper() {}

    static String label(String value) {
        return value.toUpperCase(Locale.ROOT);
    }
}
~~~

Đây là ví dụ minh họa **có `package example;`**, vì vậy cách chạy từ dự án có đường dẫn package cần khác với các ví dụ không `package` ở trên. Với cấu trúc thư mục `src/example/MainApp.java`, có thể biên dịch và chạy từ thư mục dự án như sau:

~~~bash
javac -d out src/example/MainApp.java
java -cp out example.MainApp
~~~

Stdout:

~~~text
JAVA
~~~

Trong mô hình này, `javac -d out` đặt các `.class` vào thư mục con `out/example/` theo package; `java -cp out example.MainApp` sử dụng tên lớp đầy đủ. `Helper` vẫn nằm trong **cùng tệp nguồn** với `MainApp` và cùng package.

### 6.2. Quy tắc các lớp top-level và tên tệp

- Theo cách biên dịch tệp nguồn trên filesystem thông dụng (`javac`), **chỉ một kiểu top-level được khai báo `public` trong một tệp**, và tệp cần trùng tên kiểu `public` đó: `public class MainApp` → `MainApp.java`.
- Các lớp top-level còn lại có thể khai báo không `public`, ví dụ `class Helper` hoặc `final class Helper`. Chúng dùng quyền truy cập package-private.
- **Không thể** khai báo `private class Helper` hoặc `static class Helper` ở cấp top-level. `private` và `static` ở dạng đó được dùng với lớp **lồng bên trong** một lớp khác, không phải lớp ngang hàng.
- Hai class top-level có thể gọi nhau theo quy tắc package và quyền truy cập thành viên, ngay cả khi chúng nằm trong cùng tệp.
- Lớp top-level không `public` **không bắt buộc** có cùng tên với tệp. Chỉ lớp `public` là chuẩn thuận tiện nhất để đặt tên và dùng với `javac`.
- Source-file launcher có một số quy tắc riêng về tên nguồn và cách chọn lớp so với `javac`, nhưng **đặt tên file trùng lớp chính** giúp cả hai cách chạy nhất quán và dễ hiểu.
- Không thể đặt `import` sau một khai báo lớp. Các lệnh `import` đặt phía trên các top-level declaration.

### 6.3. Gọi helper: static và non-static

Ví dụ minh họa **không phải chương trình độc lập**:

~~~java
class Demo {
    static void mainStep() {
        // Chỉ gọi thẳng được helper static.
        int doubled = doubleValue(3);

        // Helper instance phải gọi qua một đối tượng.
        Demo demo = new Demo();
        int tripled = demo.tripleValue(3);
    }

    private static int doubleValue(int n) {
        return n * 2;
    }

    private int tripleValue(int n) {
        return n * 3;
    }
}
~~~

Trong `static main`, muốn gọi một phương thức instance phải có object phù hợp. Thêm `static` cho mọi phương thức chỉ để tránh tạo object là không đúng khi helper thật sự cần trạng thái của từng instance.

## 7. Cách thiết kế main và helper để chương trình dễ phát triển

Một bố cục thực dụng cho chương trình một tệp:

1. `main` thực hiện **đọc đối số / nhận input**, gọi helper với dữ liệu hợp lệ và **in kết quả hoặc xử lý lỗi ở ranh giới CLI**.
2. Helper thực hiện **một nhiệm vụ cụ thể**, đặt tên theo kết quả/hành động (`parseThreshold`, `countAtLeast`, `formatResult`), nhận dữ liệu qua tham số và trả kết quả rõ ràng.
3. Ưu tiên helper **không phụ thuộc vào input/output hoặc biến toàn cục**, nhất là các phép tính thuần. Các helper này có thể test chỉ bằng input và output.
4. Dùng `private` cho helper method chỉ nội bộ; dùng package-private cho helper class top-level cần dùng trong cùng package; dùng nested private class nếu cần giới hạn phạm vi sâu hơn.
5. Hạn chế `static` mutable fields chia sẻ trạng thái giữa các lời gọi. Với chương trình cần lưu trạng thái, truyền một object hoặc tạo class có instance state rõ ràng.
6. Khi helper trở nên nhiều, được nhiều lớp sử dụng hoặc có vòng đời/test riêng, **tách ra tệp mới** cùng package hoặc kiến trúc dự án phù hợp; “một tệp” chỉ là cách tổ chức hợp lý khi phạm vi chương trình còn nhỏ.

Trong `ScoreReport`, phép tính trung bình **không** cần biết đối số dòng lệnh đến từ đâu, cũng không tự định dạng kết quả. Ngược lại, `main` không cần quan tâm thuật toán đếm phần tử. Hai trách nhiệm tách rời giúp đổi giao diện CLI mà không phải sửa thuật toán, hoặc test thuật toán mà không phải chạy toàn chương trình.

## 8. Lỗi thường gặp và cách sửa

| Triệu chứng hoặc cách làm sai | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `javac` báo lớp `public` phải nằm trong tệp cùng tên | Tệp `A.java` chứa `public class B` | Đổi tệp thành `B.java` hoặc chỉnh tên lớp chính cho khớp |
| `javac` báo có hai lớp `public` trong một tệp | Vi phạm quy tắc tệp top-level trên filesystem | Giữ một lớp top-level `public`, các helper còn lại package-private, hoặc tách tệp |
| `non-static method ... cannot be referenced from a static context` | Gọi helper instance trực tiếp từ `static main` | Nếu logic không cần state, cân nhắc `static`; nếu cần state, tạo object rồi gọi |
| `java ScoreReport` báo không tìm thấy main class | Chưa biên dịch hoặc đang dùng sai classpath/package | Chạy `javac` trước và dùng đúng tên class/package; hoặc chạy `java ScoreReport.java` |
| `java ScoreReport.java` không chạy đúng main | Lớp top-level đầu tiên trong tệp nguồn không phải lớp main | Đặt lớp khởi động trước các helper top-level |
| Helper không nhìn thấy vì khai báo `private` sai chỗ | Đang nhầm lớp top-level với lớp nested | Lớp top-level thường package-private; nested helper mới có thể là `private static class` |
| `NumberFormatException` khi đọc `args[0]` | Đối số là chuỗi không thể phân tích thành số | Kiểm tra số lượng đối số và bắt/giải thích lỗi parse gần ranh giới CLI |
| Đổi source nhưng `java MainClass` vẫn cho kết quả cũ | Chưa biên dịch lại, đang chạy `.class` cũ | Chạy `javac MainClass.java` trước khi chạy bằng tên class |
| Test phụ thuộc dấu thập phân của môi trường | `printf` dùng locale mặc định | Truyền `Locale.ROOT` khi cần output có định dạng cố định |
| Helper tự `System.exit` hoặc ghi console ở khắp nơi | Trộn xử lý nghiệp vụ với điều phối | Để helper trả giá trị/throw lỗi hợp lý, `main` quyết định hiển thị và mã thoát |
| Coi source launcher của mọi JDK có đúng các giới hạn của Java 11 | Các bản JDK sau đã hỗ trợ nhiều tệp nguồn | Dựa theo tài liệu launcher **đúng JDK đang chạy** và yêu cầu của dự án |

Không nên đè các lớp khác nhau bằng tên trùng nhau trong cùng package, dù chúng nằm trong các tệp hay cùng tệp; Java định danh class theo tên và package, không phải theo khối văn bản.

## 9. Tự kiểm tra với ba bài thực hành

**Bài 1 — helper method trong một class.** Sửa `GreetingApp` để nhận hai đối số `firstName` và `lastName` rồi gọi `private static String fullName(...)`. Hãy bảo đảm `main` chỉ đọc và hiển thị, còn ghép tên nằm trong helper. Dự kiến `java GreetingApp.java An Nguyen` in `Hello, An Nguyen!` nếu bạn giữ `makeGreeting` như ở mục 2 và bổ sung cách ghép tên.

**Bài 2 — helper class thứ hai trong cùng tệp.** Với `ScoreReport.java`, viết thêm `static int maximum(int[] values)` trong `ScoreMath`, yêu cầu mảng không rỗng. Gọi helper từ `main` và thêm dòng `max=10` sau ba dòng hiện có. Giữ một lớp top-level `public`, và so sánh cả hai cách chạy.

**Bài 3 — nhận diện lỗi chọn lớp.** Di chuyển toàn bộ khai báo `ScoreMath` lên trước `ScoreReport` trong chính một tệp (chỉ trong bản thử nghiệm). So sánh `java ScoreReport.java` với `javac ScoreReport.java` rồi `java ScoreReport`. Giải thích tại sao chế độ source-file có thể gặp lỗi chọn điểm vào dù bản đã biên dịch vẫn chạy đúng bằng tên class.

### Checklist hoàn thành

- Tên tệp, lớp `public` và lệnh chạy khớp nhau.
- `main` nằm trong lớp dự định khởi động; với `java File.java`, lớp ấy đứng trước top-level helper.
- Các `import` nằm trước các khai báo class; nếu có `package` thì package đứng đầu.
- Helper chỉ nhận trách nhiệm phù hợp, có phạm vi truy cập nhỏ nhất có thể.
- Không nhầm `static` với instance và không nhầm top-level helper với nested helper.
- Đã thử cả `java File.java` và `javac` → `java ClassName` khi môi trường yêu cầu.
- Đã kiểm tra stdout, lỗi nhập đối số và mức Java mục tiêu.
- Khi dùng tài liệu online, đã đối chiếu đúng phiên bản Java thay vì suy rộng hành vi cũ sang JDK mới.

## Tài liệu tham khảo chính thức và còn áp dụng

- [Oracle: Lệnh `java` trong Java 11](https://docs.oracle.com/en/java/javase/11/tools/java.html) — `main`, source-file mode, chọn lớp đầu tiên và cách chuyển đối số.
- [Oracle: Lệnh `javac` trong Java 11](https://docs.oracle.com/en/java/javase/11/tools/javac.html) — biên dịch source file và tùy chọn biên dịch.
- [Java Language Specification `7 (Java 11)](https://docs.oracle.com/javase/specs/jls/se11/html/jls-7.html) — compilation unit, `package`, `import`, nhiều khai báo top-level và ràng buộc tên tệp.
- [OpenJDK JEP 330](https://openjdk.org/jeps/330) — tính năng chạy trực tiếp một tệp nguồn ra mắt trong Java 11.
- [Oracle: Lệnh `java` trong Java 25](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html) — cách source launcher hiện đại hoạt động và những thay đổi mở rộng.
- [Dev.java: Launching Simple Source-Code Programs](https://dev.java/learn/first-steps/first-java-code/launch-simple-source-code-programs/) — hướng dẫn hiện tại, gồm chạy chương trình nhiều tệp từ JDK 22.

**Ghi nhớ:** Với bài Java 11 trong **một file**, dùng `main` rõ ràng, đặt helper gần nơi sử dụng, chọn phạm vi truy cập hợp lý và để tên lớp/tệp/lệnh chạy nhất quán. Khi chức năng lớn lên, tách lớp thành tệp riêng là bước phát triển tự nhiên, nhưng các nguyên tắc chia trách nhiệm vẫn giữ nguyên.