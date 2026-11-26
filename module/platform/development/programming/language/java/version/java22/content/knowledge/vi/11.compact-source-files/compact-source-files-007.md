# Chạy tệp nguồn gọn và phân biệt với cơ chế chạy chương trình nhiều tệp của JEP 458

## 1. Phân biệt cú pháp nguồn và cách khởi chạy

Trong chương **Tệp nguồn gọn** của module `JAVA_VERSION_JAVA22`, mục tiêu là hiểu những thay đổi từ giai đoạn Java 22 vẫn hữu ích khi làm việc với Java hiện đại. Khi nhìn thấy lệnh `java App.java`, hãy đặt hai câu hỏi riêng:

- **Tệp viết theo cú pháp nào?** Có khai báo lớp tường minh hay dùng tệp nguồn gọn với `main` nằm ngoài khai báo lớp?
- **Chương trình được khởi chạy thế nào?** Launcher biên dịch nguồn để chạy ngay, hay nạp bytecode đã được biên dịch trước?

Tệp nguồn gọn giảm phần khai báo khi viết chương trình nhỏ. Cơ chế chạy chương trình nhiều tệp của JEP 458 giúp launcher tìm và biên dịch thêm nguồn phụ thuộc. Hai khả năng có thể kết hợp trong cùng chương trình. [Oracle: tệp nguồn gọn](https://docs.oracle.com/en/java/javase/25/language/compact-source-files-instance-main-methods.html), [Dev.java: chạy chương trình từ mã nguồn](https://dev.java/learn/first-steps/first-java-code/launch-simple-source-code-programs/).

## 2. Chọn đúng mốc phiên bản

| Khả năng | Trong Java 22 | Mốc dùng ổn định trong bài |
| --- | --- | --- |
| Chạy trực tiếp một tệp `.java` | Đã có từ trước Java 22 | Tiếp tục sử dụng |
| Tự tìm và biên dịch nguồn phụ thuộc theo JEP 458 | Tính năng chính thức từ Java 22 | Java 22 trở lên |
| Lớp được khai báo ngầm và instance `main` của JEP 463 | Preview lần hai | Dùng dạng chính thức của JEP 512 từ Java 25 |

Tên **compact source files** là tên chính thức từ Java 25. Vì yêu cầu chỉ học kiến thức còn áp dụng, các ví dụ chính dùng Java 25 trở lên; tùy chọn preview của Java 22 chỉ xuất hiện để giải thích cách chạy đúng trên phiên bản đó. `public static void main(String[] args)` vẫn hợp lệ và hữu ích. [Oracle: tính năng ngôn ngữ theo phiên bản](https://docs.oracle.com/en/java/javase/25/language/java-language-changes-release.html).

Kiểm tra JDK mà terminal đang sử dụng:

```powershell
java --version
javac --version
```

Nếu IDE chạy được nhưng terminal báo lỗi, hãy so sánh JDK và mức ngôn ngữ của hai môi trường trước khi thay đổi mã.

## 3. Chạy một tệp nguồn gọn

Tạo `Greeting.java`:

```java
void main(String[] args) {
    String name = args.length == 0 ? "ban" : args[0];
    System.out.println("Xin chao, " + name);
}
```

Với JDK 25 trở lên, chạy trong thư mục chứa tệp:

```powershell
java Greeting.java Lan
```

Kết quả dự kiến:

```text
Xin chao, Lan
```

Đây là tệp nguồn gọn vì phương thức được viết ngoài khai báo lớp tường minh. Compiler vẫn tạo lớp ngầm chứa phương thức; chương trình vẫn chạy bằng JVM. Dùng `System.out.println` trong ví dụ giúp giữ cùng đoạn mã khi đối chiếu với Java 22. [Oracle: compact source files](https://docs.oracle.com/en/java/javase/25/language/compact-source-files-instance-main-methods.html).

Trên **đúng JDK 22**, cần bật preview:

```powershell
java --enable-preview --source 22 Greeting.java Lan
```

Không dùng lệnh này để yêu cầu JDK mới tái hiện preview cũ. Preview gắn với phiên bản JDK của nó; khi chuyển sang JDK hiện đại, hãy dùng dạng ngôn ngữ đã chính thức hóa. [Oracle: preview features của Java 22](https://docs.oracle.com/en/java/javase/22/language/preview-language-and-vm-features.html).

### Source-file mode vẫn có bước biên dịch

Với `java Greeting.java`, launcher biên dịch nguồn trong bộ nhớ rồi thực thi. Bạn không cần chạy `javac` riêng và không nhận được bộ tệp `.class` lưu trên đĩa để phân phối. Dùng đường dẫn có khoảng trắng thì đặt đường dẫn trong dấu nháy:

```powershell
java "H:\Java demos\Greeting.java" Lan
```

Đường dẫn đến nguồn không tự đổi thư mục làm việc của chương trình. [Oracle: source-file mode](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html#using-source-file-mode-to-launch-source-code-programs).

### Có thể biên dịch tệp nguồn gọn trước

Trên JDK 25 trở lên, có thể chọn quy trình hai bước:

```powershell
javac Greeting.java
java Greeting Lan
```

Trong cách này, `javac` tạo `Greeting.class`; lệnh sau nạp lớp đã biên dịch. Lệnh `java Greeting.java Lan` và `java Greeting Lan` biểu đạt hai cách khởi chạy khác nhau. [Oracle: chạy compact source files](https://docs.oracle.com/en/java/javase/26/language/compact-source-files-instance-main-methods.html).

## 4. Launcher chọn `main` như thế nào?

Ở dạng chính thức từ Java 25, phương thức `main` ứng viên trả về `void`, không có mức truy cập `private`, và nhận `String[]` hoặc không nhận tham số. Phương thức có thể là `static` hoặc instance. Nếu có cả hai dạng tham số hợp lệ, launcher ưu tiên dạng nhận `String[]`, kể cả khi không truyền đối số. [JLS 25, §12.1.4](https://docs.oracle.com/javase/specs/jls/se25/html/jls-12.html#jls-12.1.4).

Ví dụ độc lập `EntryChoice.java`:

```java
void main() {
    System.out.println("Khong tham so");
}

void main(String[] args) {
    System.out.println("So doi so: " + args.length);
}
```

```powershell
java EntryChoice.java
```

Kết quả dự kiến:

```text
So doi so: 0
```

Nếu chọn instance `main`, launcher tạo đối tượng rồi gọi phương thức đó. Tệp nguồn gọn có constructor mặc định không tham số. Khi chỉ cần một điểm vào, nên khai báo một `main` để người đọc không phải phân tích quy tắc chọn phương thức. [Oracle: giao thức chạy tệp nguồn gọn](https://docs.oracle.com/en/java/javase/27/language/compact-source-files-instance-main-methods.html).

## 5. JEP 458 mở rộng điều gì?

Từ Java 22, source launcher có thể tìm, biên dịch và nạp các tệp nguồn phụ thuộc theo cấu trúc package. Khả năng này cũng hoạt động với chương trình khai báo lớp và `public static void main(String[] args)` thông thường; không cần cú pháp nguồn gọn. [Dev.java: multi-file source-code programs](https://dev.java/learn/first-steps/first-java-code/launch-simple-source-code-programs/).

| Câu hỏi | Tệp nguồn gọn và instance `main` | JEP 458 |
| --- | --- | --- |
| Tác động chính | Cách viết nguồn và khai báo điểm vào | Cách launcher tìm và chạy nguồn phụ thuộc |
| Phải bỏ khai báo lớp? | Có thể bỏ khi dùng tệp nguồn gọn | Không |
| Phải có nhiều tệp? | Không | Chỉ phát huy phần mở rộng khi cần thêm nguồn |
| Có thể kết hợp? | Tệp gọn làm điểm vào | Launcher tìm các lớp phụ trợ được tham chiếu |

Bảng trên là cách phân biệt để đọc ví dụ: **nguồn gọn** mô tả hình thức mã; **nhiều tệp** mô tả tổ chức chương trình mà launcher xử lý.

## 6. Ví dụ kết hợp: tệp gọn gọi lớp trong package

Giả sử có thư mục `demo` chứa hai tệp, chưa có bytecode biên dịch trước và không có khai báo module:

```text
demo/
├── App.java
└── shop/
    └── pricing/
        └── PriceCalculator.java
```

Nội dung `App.java`:

```java
import shop.pricing.PriceCalculator;

void main(String[] args) {
    int quantity = args.length == 0 ? 1 : Integer.parseInt(args[0]);
    long total = PriceCalculator.total(quantity);
    System.out.println("Tong tien: " + total + " VND");
}
```

Nội dung `shop/pricing/PriceCalculator.java`:

```java
package shop.pricing;

public final class PriceCalculator {
    public static long total(int quantity) {
        if (quantity < 0) {
            throw new IllegalArgumentException("quantity must be non-negative");
        }
        return 120_000L * quantity;
    }
}
```

Từ thư mục `demo`, trên JDK 25 trở lên:

```powershell
java App.java 3
```

Kết quả dự kiến:

```text
Tong tien: 360000 VND
```

Ở đây, `App.java` thể hiện cú pháp nguồn gọn. Việc tìm `shop/pricing/PriceCalculator.java` theo tham chiếu `shop.pricing.PriceCalculator` thể hiện khả năng nhiều tệp của launcher. Cách ánh xạ package sang thư mục được mô tả trong [hướng dẫn launcher Java 22](https://docs.oracle.com/en/java/javase/22/docs/specs/man/java.html#using-source-file-mode-to-launch-source-code-programs).

Vẫn với hai tệp này, trên **JDK 22**:

```powershell
java --enable-preview --source 22 App.java 3
```

Cờ preview cần cho phần nguồn gọn của JEP 463. JEP 458 tự nó đã chính thức trong Java 22. Phạm vi preview của JEP 463 được nêu trong [hướng dẫn ngôn ngữ Java 22](https://docs.oracle.com/en/java/javase/22/language/implicitly-declared-classes-and-instance-main-methods.html).

## 7. JEP 458 cũng chạy được điểm vào có lớp tường minh

Giữ `PriceCalculator.java`, thêm `shop/cli/Main.java`:

```text
demo/
├── App.java
└── shop/
    ├── cli/
    │   └── Main.java
    └── pricing/
        └── PriceCalculator.java
```

Nội dung tệp mới:

```java
package shop.cli;

import shop.pricing.PriceCalculator;

public class Main {
    public static void main(String[] args) {
        int quantity = args.length == 0 ? 1 : Integer.parseInt(args[0]);
        System.out.println("Tong tien: " + PriceCalculator.total(quantity) + " VND");
    }
}
```

Từ `demo`, dùng JDK 22 trở lên:

```powershell
java shop/cli/Main.java 3
```

Kết quả vẫn là `Tong tien: 360000 VND`. Không cần bật preview: điểm vào này dùng cú pháp đã ổn định, còn launcher nhiều tệp có sẵn từ Java 22. Việc có `App.java` bên cạnh không biến nó thành điểm vào thứ hai của lần chạy này.

### Thư mục gốc nguồn được suy ra thế nào?

Với đường dẫn `demo/shop/cli/Main.java` và khai báo `package shop.cli`, launcher suy ra gốc nguồn là `demo`. Từ đó, nó có thể tìm `shop.pricing.PriceCalculator` ở `demo/shop/pricing/PriceCalculator.java`. [Oracle: quy tắc source root](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html#using-source-file-mode-to-launch-source-code-programs).

Trong ví dụ tệp gọn, `App.java` không khai báo package, nên thư mục chứa nó là gốc nguồn cho cấu trúc đang minh họa. Vì vậy, hãy đặt các lớp phụ trợ theo đúng package bên dưới thư mục này.

Đừng hiểu launcher như công cụ quét và build mọi tệp trong repository. Với cây ví dụ trên, lệnh chỉ định một tệp khởi chạy, rồi các nguồn cần thiết được tìm từ quan hệ phụ thuộc và gốc nguồn. Đây là hệ quả của quy tắc tìm nguồn, không phải cấu hình một dự án Maven hay Gradle.

## 8. Đối số sau tên tệp thuộc về chương trình

Cấu trúc lệnh:

```text
java [tùy chọn launcher] <tệp nguồn khởi chạy> [đối số chương trình]
```

Trong `java App.java 3`, giá trị `3` là `args[0]`. Các tùy chọn như `--class-path` phải xuất hiện trước tệp khởi chạy. [Oracle: cú pháp lệnh java](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html#synopsis).

Ví dụ dễ gây hiểu nhầm, dùng lại `Greeting.java`:

```powershell
java Greeting.java Extra.java
```

Kết quả dự kiến là `Xin chao, Extra.java`: chuỗi `Extra.java` được chương trình dùng làm tên người nhận. Lệnh này không yêu cầu launcher biên dịch hai tệp khởi chạy. Từ quy tắc đối số, cũng suy ra rằng:

```powershell
java App.java shop/pricing/PriceCalculator.java
```

sẽ khiến ví dụ tính tiền thử chuyển chuỗi đường dẫn thành số lượng và phát sinh `NumberFormatException`.

## 9. Nguồn phụ thuộc và thư viện đã biên dịch

Source launcher có thể dùng thư viện JAR được cung cấp qua classpath. Ví dụ giả định chương trình dùng API trong hai JAR đã có trên máy, chạy từ thư mục chứa `App.java` và `lib`:

```powershell
java --class-path "lib/library-a.jar;lib/library-b.jar" App.java 3
```

Windows dùng `;` ngăn cách phần tử classpath; Linux và macOS dùng `:`. Các JAR phải được chuẩn bị trước. Đặt JAR lên classpath giúp tìm bytecode, còn `import` chỉ phục vụ việc tham chiếu tên trong mã nguồn. [Oracle: tùy chọn classpath](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html#standard-options-for-java), [JLS 25, §7.5](https://docs.oracle.com/javase/specs/jls/se25/html/jls-7.html#jls-7.5).

Nếu công cụ tính tiền cần thư viện đọc bảng tính, bước thêm `import` sẽ không tự tải thư viện ấy. Khi việc quản lý phiên bản và phụ thuộc trở thành một phần của bài toán, nên đưa dự án vào Maven hoặc Gradle.

## 10. Giới hạn cần biết khi mở rộng chương trình

### Tệp gọn phù hợp làm điểm vào

Lớp ngầm của tệp gọn nằm trong unnamed package, phải có `main` ứng viên và không được khai báo constructor trực tiếp. Các phương thức phụ trợ trong tệp vẫn là thành viên của lớp đó. Khi cần package cho điểm vào, hãy chuyển sang lớp tường minh như `shop.cli.Main`. [JLS 25, §8.1.8](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.1.8).

Vì thế, không nên tách `PriceCalculator.total` thành một tệp chỉ có phương thức ngoài lớp rồi mong dùng nó như thư viện. Hãy giữ lớp phụ trợ có tên rõ ràng và API phù hợp.

### Chạy nguồn không cung cấp toàn bộ quy trình build

Source-file mode tắt annotation processing và không cung cấp cơ chế truyền mọi tùy chọn compiler như `-processor` hoặc `-Werror`. [Oracle: giới hạn source-file mode](https://docs.oracle.com/en/java/javase/22/docs/specs/man/java.html#using-source-file-mode-to-launch-source-code-programs).

Với ứng dụng cần sinh mã bằng annotation processor, chạy test tự động, đóng gói JAR hoặc tạo bản build để triển khai, hãy thiết lập quy trình build tương ứng. Lệnh chạy nguồn thuận tiện cho việc học, thử API và công cụ nhỏ; artifact triển khai cần được tạo và kiểm tra riêng.

## 11. Chẩn đoán theo triệu chứng

| Triệu chứng trong các ví dụ | Kiểm tra và xử lý |
| --- | --- |
| JDK 22 từ chối `void main` ngoài lớp | Dùng đúng JDK 22 với cờ preview ở mục 3, hoặc chuyển ví dụ sang JDK 25 trở lên |
| Không tìm thấy `shop.pricing.PriceCalculator` | Đối chiếu khai báo package, đường dẫn `shop/pricing/PriceCalculator.java` và gốc nguồn ở mục 7 |
| Đã thêm tên tệp phụ vào lệnh nhưng vẫn lỗi | Xóa tên tệp đó khỏi phần đối số; để launcher tìm nguồn qua tham chiếu kiểu |
| `java Greeting` không tìm thấy lớp | Biên dịch trước bằng `javac Greeting.java`, hoặc dùng `java Greeting.java` để chạy từ nguồn |
| IDE chạy được nhưng terminal thất bại | So sánh JDK, classpath và thư mục làm việc |
| Mã phụ thuộc vào lớp sinh tự động nhưng chạy nguồn thất bại | Dùng quy trình build có bước sinh mã cần thiết |

Các bước trên áp dụng trực tiếp cho ví dụ của bài; thông báo lỗi cụ thể có thể khác giữa các JDK.

## 12. Chọn cách chạy theo nhu cầu

| Nhu cầu | Cách chọn |
| --- | --- |
| Thử nhanh một thuật toán trong một tệp trên JDK 25 trở lên | Viết tệp nguồn gọn, chạy `java TenTep.java` |
| Chia bài tập thành vài lớp có package | Dùng cấu trúc nguồn đúng package và launcher nhiều tệp của Java 22 trở lên |
| Muốn điểm vào ngắn nhưng vẫn tách logic | Kết hợp tệp gọn với các lớp phụ trợ tường minh |
| Cần kiểm tra đầu ra bytecode trước khi chạy | Dùng `javac`, sau đó chạy lớp đã biên dịch |
| Cần quản lý phụ thuộc, test, sinh mã và đóng gói | Dùng quy trình build của dự án |

Để tự xác nhận đã phân biệt được hai khả năng, hãy giải thích lệnh `java App.java 3` bằng ba ý: `App.java` dùng cú pháp gì, lớp phụ trợ được tìm ở đâu, và giá trị nào được truyền vào `main`. Trong ví dụ tính tiền, câu trả lời lần lượt là tệp nguồn gọn, đường dẫn theo package dưới gốc `demo`, và chuỗi `"3"`.
