# Phạm vi ngôn ngữ, thư viện chuẩn, JVM và công cụ của JDK 21

Java 21 là một bản phát hành LTS (Long-Term Support) của nền tảng Java. Khi nói một ứng dụng “dùng Java 21”, cần phân biệt bốn lớp liên quan: ngôn ngữ Java mà lập trình viên viết, thư viện chuẩn mà chương trình gọi, máy ảo Java (JVM) thực thi bytecode, và bộ công cụ JDK dùng để phát triển, đóng gói, chẩn đoán và vận hành ứng dụng. Bốn lớp phối hợp với nhau nhưng có vai trò và chu kỳ thay đổi riêng.

Bài này xác định phạm vi của Java 21 để biết một tính năng hoặc lỗi thuộc lớp nào, cần tra cứu tài liệu nào và chọn công cụ nào. Các nội dung tập trung vào tính năng đã được chuẩn hóa và còn có ý nghĩa khi phát triển ứng dụng; những tính năng thử nghiệm (preview/incubator) của một bản phát hành không được xem là nền tảng ổn định để xây dựng kiến thức cốt lõi.

## 1. Bốn lớp tạo nên nền tảng Java 21

| Lớp | Trách nhiệm | Ví dụ |
|---|---|---|
| Ngôn ngữ Java | Quy tắc cú pháp, kiểu dữ liệu, biểu thức, câu lệnh và cấu trúc chương trình | class, interface, generic, record, pattern matching |
| Thư viện chuẩn Java SE | Các kiểu và API có sẵn để xử lý công việc phổ biến | `java.lang`, `java.util`, `java.io`, `java.nio`, `java.net`, `java.time`, `java.util.concurrent` |
| JVM | Nạp, xác minh và thực thi bytecode; quản lý bộ nhớ và phối hợp với hệ điều hành | class loading, garbage collection, JIT compilation, thread |
| JDK | Phân phối môi trường phát triển, gồm runtime và các công cụ phát triển/vận hành | `java`, `javac`, `jar`, `javadoc`, `jshell`, `jlink`, `jpackage`, `jcmd` |

### 1.1. Ngôn ngữ Java

Ngôn ngữ quy định cách viết chương trình và ý nghĩa của mã nguồn. Nó bao gồm hệ thống kiểu, biến, toán tử, điều khiển luồng, lớp, interface, kế thừa, ngoại lệ, generic, annotation, lambda, record và các cấu trúc khác.

Java 21 tiếp tục hỗ trợ mô hình lập trình hướng đối tượng, đồng thời cung cấp các cấu trúc biểu đạt hiện đại hơn. Những điểm nổi bật đã trở thành tính năng chính thức trong Java 21 gồm:

- **Record patterns**: cho phép khớp mẫu và tách thành phần của một record trong điều kiện hoặc biểu thức `instanceof`, cũng như trong `switch`.
- **Pattern matching for switch**: cho phép dùng mẫu kiểu trong nhánh `case`, kết hợp với guard bằng `when` khi cần điều kiện bổ sung.
- **Virtual threads**: là tính năng của nền tảng đồng thời, được sử dụng qua API Java; chúng không làm thay đổi cú pháp ngôn ngữ cốt lõi.

Ví dụ về pattern matching trong `switch`:

```java
static String describe(Object value) {
    return switch (value) {
        case null -> "không có giá trị";
        case String text -> "chuỗi có " + text.length() + " ký tự";
        case Integer number when number >= 0 -> "số nguyên không âm: " + number;
        case Integer number -> "số nguyên âm: " + number;
        default -> "kiểu dữ liệu khác";
    };
}
```

Ví dụ về record pattern:

```java
record Point(int x, int y) {}

static int manhattanDistance(Object value) {
    if (value instanceof Point(int x, int y)) {
        return Math.abs(x) + Math.abs(y);
    }
    throw new IllegalArgumentException("Giá trị không phải Point");
}
```

Các ví dụ này minh họa khả năng của ngôn ngữ Java 21; chúng không yêu cầu thư viện bên ngoài.

### 1.2. Thư viện chuẩn Java SE

Thư viện chuẩn cung cấp các API đã được định nghĩa để ứng dụng không phải tự xây dựng lại những chức năng nền tảng. Một số nhóm thường dùng:

| Nhóm package | Phạm vi tiêu biểu |
|---|---|
| `java.lang` | Kiểu cơ bản, `Object`, `String`, `Math`, ngoại lệ nền tảng và các lớp runtime |
| `java.util` | Collections, Optional, random, formatter và tiện ích |
| `java.util.stream` | Xử lý dữ liệu theo pipeline với Stream API |
| `java.util.concurrent` | Executor, Future, đồng bộ hóa và tiện ích lập trình đồng thời |
| `java.io` | Luồng vào/ra và serialization API |
| `java.nio`, `java.nio.file` | Buffer, channel, thao tác file và hệ thống tệp |
| `java.net`, `java.net.http` | Kết nối mạng và HTTP Client |
| `java.time` | Ngày, giờ, múi giờ và khoảng thời gian |
| `java.sql` | API kết nối cơ sở dữ liệu JDBC |
| `java.security`, `javax.crypto` | Bảo mật, chứng thư và mật mã |

Java 21 bổ sung **Sequenced Collections**: một nhóm interface trong Collections Framework biểu diễn collection có thứ tự xác định và cung cấp thao tác nhất quán ở hai đầu. Các interface tiêu biểu là `SequencedCollection`, `SequencedSet` và `SequencedMap`. Chúng giúp viết mã tổng quát hơn khi cần truy cập phần tử đầu/cuối hoặc đảo chiều thứ tự.

Ví dụ:

```java
import java.util.ArrayList;
import java.util.SequencedCollection;

class Main {
    public static void main(String[] args) {
        SequencedCollection<String> names = new ArrayList<>();
        names.addFirst("An");
        names.addLast("Bình");

        System.out.println(names.getFirst()); // An
        System.out.println(names.getLast());  // Bình
        System.out.println(names.reversed()); // [Bình, An]
    }
}
```

API thư viện chuẩn có thể được mở rộng qua các bản Java, vì vậy cần đối chiếu tài liệu API đúng phiên bản khi chọn phương thức hoặc package. Một thư viện của bên thứ ba, chẳng hạn framework web hay thư viện kết nối database cụ thể, không tự động trở thành một phần của Java SE chỉ vì nó chạy trên JDK.

### 1.3. JVM

JVM là môi trường thực thi bytecode Java. Trình biên dịch `javac` chuyển mã nguồn thành các file `.class`; JVM nạp và thực thi bytecode đó. Vì bytecode và hợp đồng của JVM được đặc tả, cùng một ứng dụng có thể chạy trên các JVM tương thích ở nhiều hệ điều hành và kiến trúc phần cứng.

Các trách nhiệm chính của JVM gồm:

- **Class loading và linking**: tìm, nạp, kiểm tra và chuẩn bị lớp trước khi sử dụng.
- **Bytecode verification**: kiểm tra cấu trúc và các ràng buộc an toàn của bytecode.
- **Execution engine**: diễn giải bytecode và có thể biên dịch các đoạn mã thường chạy sang mã máy bằng JIT compiler.
- **Memory management**: quản lý heap, stack của từng luồng và các vùng dữ liệu runtime.
- **Garbage collection (GC)**: thu hồi bộ nhớ của đối tượng không còn được tham chiếu theo các quy tắc của bộ thu gom rác.
- **Runtime services**: hỗ trợ luồng, đồng bộ hóa, xử lý ngoại lệ, liên kết native và các dịch vụ runtime khác.

JVM không đồng nghĩa với toàn bộ JDK. JVM là một phần của môi trường chạy Java; JDK còn cung cấp trình biên dịch, công cụ đóng gói, tài liệu và công cụ chẩn đoán.

Java 21 có các cải tiến runtime đáng chú ý như virtual threads đã chính thức và Generational ZGC. Virtual threads được quản lý bởi runtime Java và phù hợp với ứng dụng có nhiều tác vụ đồng thời chủ yếu chờ I/O. Chúng giúp giảm chi phí tạo và quản lý luồng ở quy mô lớn, nhưng không làm cho thao tác CPU-bound chạy nhanh hơn một cách tự động và cũng không loại bỏ giới hạn của database, network hay dịch vụ phụ thuộc.

Ví dụ tạo virtual threads bằng API chuẩn:

```java
import java.util.concurrent.Executors;

class Main {
    public static void main(String[] args) throws Exception {
        try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
            var first = executor.submit(() -> "tác vụ thứ nhất");
            var second = executor.submit(() -> "tác vụ thứ hai");

            System.out.println(first.get());
            System.out.println(second.get());
        }
    }
}
```

### 1.4. JDK

JDK (Java Development Kit) là bộ công cụ để phát triển và làm việc với ứng dụng Java. Một bản JDK 21 cung cấp runtime Java 21 cùng các công cụ dòng lệnh và thành phần phát triển. Nhà cung cấp có thể phân phối JDK với cách đóng gói, giấy phép và chính sách cập nhật riêng; khi cài đặt cho dự án, cần xác định rõ nhà cung cấp, phiên bản cập nhật và hệ điều hành mục tiêu.

Một số công cụ thường gặp:

| Công cụ | Công dụng |
|---|---|
| `java` | Khởi chạy ứng dụng hoặc chạy mã nguồn đơn giản |
| `javac` | Biên dịch mã nguồn Java thành bytecode |
| `jshell` | Thử nghiệm biểu thức và đoạn mã Java tương tác |
| `jar` | Tạo, xem và thao tác với file JAR |
| `javadoc` | Sinh tài liệu API từ comment và khai báo mã nguồn |
| `jlink` | Tạo runtime image tùy biến từ các module |
| `jpackage` | Đóng gói ứng dụng thành định dạng cài đặt phù hợp nền tảng |
| `jdeps` | Phân tích phụ thuộc package và module |
| `jcmd` | Gửi lệnh chẩn đoán tới tiến trình JVM |
| `jstack` | Lấy thread dump để phân tích trạng thái luồng |
| `jmap` | Lấy thông tin về heap và heap dump trong các tình huống hỗ trợ |
| `jfr` | Làm việc với bản ghi Java Flight Recorder |

Không phải mọi công cụ đều cần trong mỗi dự án. Lập trình viên thường dùng `java` và `javac` ở mức cơ bản; các công cụ như `jcmd`, `jstack` và `jfr` trở nên hữu ích khi điều tra hiệu năng hoặc sự cố production.

## 2. Ranh giới giữa Java SE, JVM và JDK

Java SE định nghĩa nền tảng ở cấp ngôn ngữ, API và hành vi runtime mà ứng dụng Java chuẩn có thể dựa vào. Đặc tả ngôn ngữ (JLS) mô tả cú pháp và ngữ nghĩa; đặc tả JVM (JVMS) mô tả bytecode và hành vi máy ảo; tài liệu API mô tả các lớp và interface công khai.

JDK là bộ triển khai và công cụ phục vụ phát triển. Một JDK có thể chứa cách triển khai JVM, thư viện Java SE và các công cụ. Do đó, khi đọc tài liệu hoặc xử lý lỗi, hãy xác định đúng lớp:

- Lỗi cú pháp, kiểu hoặc quy tắc `switch`: kiểm tra ngôn ngữ và phiên bản source level.
- Không tìm thấy class hoặc method: kiểm tra classpath/module path, phiên bản API và dependency.
- Lỗi GC, heap, thread hoặc JIT: kiểm tra cấu hình và hành vi JVM.
- Không biên dịch, đóng gói hoặc chẩn đoán được: kiểm tra công cụ JDK và cách gọi lệnh.

## 3. Phiên bản Java 21 ảnh hưởng đến build và runtime như thế nào?

Để dự án thực sự biên dịch theo Java 21, cần cấu hình toolchain và mức phát hành phù hợp trong hệ thống build. Với trình biên dịch trực tiếp, tùy chọn `--release 21` yêu cầu `javac` biên dịch theo quy tắc ngôn ngữ, bytecode và API công khai của Java 21:

```bash
javac --release 21 Main.java
java Main
```

Chỉ đặt biến môi trường hoặc cài JDK 21 không đảm bảo mọi bước build đều dùng JDK đó. Hệ thống build, IDE, CI và môi trường triển khai cần thống nhất phiên bản toolchain. Nếu biên dịch bằng JDK mới hơn nhưng ứng dụng phải chạy trên Java 21, `--release 21` (hoặc cấu hình tương đương của build tool) giúp tránh vô tình phụ thuộc API chỉ có ở phiên bản mới hơn.

Cần phân biệt ba mốc:

1. **JDK dùng để chạy compiler/build**: phiên bản bộ công cụ thực hiện quá trình build.
2. **Mức phát hành khi biên dịch**: phiên bản ngôn ngữ, bytecode và API mục tiêu.
3. **Runtime dùng khi chạy ứng dụng**: môi trường thực thi thực tế trên máy đích.

Ba mốc này có thể khác nhau trong một số pipeline. Điều quan trọng là artifact đầu ra phải tương thích với runtime được hỗ trợ và mọi dependency cũng phải tương thích.

## 4. Cách xác định phạm vi khi học và phát triển với Java 21

Khi gặp một khái niệm mới, hãy đặt nó vào đúng lớp trước khi áp dụng:

- Nếu đó là cách viết biểu thức, khai báo kiểu hoặc điều khiển luồng, hãy xác định nó thuộc ngôn ngữ Java và có phải tính năng chính thức trong Java 21 hay không.
- Nếu đó là class, interface hoặc method được import, hãy xác định package và kiểm tra tài liệu API Java 21; đồng thời phân biệt API chuẩn với thư viện bên ngoài.
- Nếu đó là cách bộ nhớ, luồng hoặc bytecode được xử lý, hãy xem xét JVM và cấu hình runtime.
- Nếu đó là lệnh biên dịch, chạy, đóng gói hoặc chẩn đoán, hãy xác định công cụ JDK tương ứng và kiểm tra phiên bản công cụ.

Một cách kiểm tra cài đặt cơ bản:

```bash
java -version
javac -version
```

Hai lệnh này cho biết phiên bản runtime và compiler đang được phân giải từ môi trường dòng lệnh hiện tại. Nếu kết quả không phải Java 21, hãy kiểm tra đường dẫn thực thi và cấu hình toolchain của dự án trước khi kết luận mã nguồn không tương thích.

## 5. Phạm vi kiến thức của module Java 21

Trong module này, “Java 21” được hiểu là nền tảng phát triển và chạy ứng dụng dựa trên JDK 21, gồm:

- Ngôn ngữ Java và các tính năng chính thức có trong phiên bản 21.
- API chuẩn Java SE 21, cách sử dụng và giới hạn tương thích của chúng.
- JVM: bytecode, class loading, thực thi, quản lý bộ nhớ, GC và concurrency runtime.
- JDK: cài đặt, lựa chọn toolchain, biên dịch, chạy, đóng gói, tài liệu và chẩn đoán.
- Quan hệ giữa phiên bản build, mức phát hành bytecode/API và runtime triển khai.

Các framework, máy chủ ứng dụng, thư viện của bên thứ ba, quy trình DevOps và dịch vụ cloud có thể được dùng cùng Java 21, nhưng thuộc phạm vi riêng của chúng. Khi học một công nghệ như vậy, cần ghi rõ đó là công nghệ tích hợp với Java 21 hay thành phần của chính nền tảng Java.

