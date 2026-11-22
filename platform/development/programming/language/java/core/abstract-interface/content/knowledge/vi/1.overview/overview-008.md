# Phạm vi Java Core và cách đối chiếu phiên bản JDK khi học abstraction/interface

## 1. Đọc đúng phạm vi của bài

Trong chủ đề **Java Core – abstract/interface**, “Java Core” được hiểu là các **khái niệm ngôn ngữ Java và API nền tảng Java SE** cần để thiết kế, cài đặt và sử dụng trừu tượng hóa. Bài tập trung vào cách Java định nghĩa kiểu và hợp đồng, cách lớp triển khai chúng, cách quy tắc ngôn ngữ thay đổi giữa các phiên bản JDK và cách tự kiểm chứng khi tài liệu hoặc IDE cho kết quả khác nhau.

Những nội dung **nằm trong phạm vi chính**:

- **Cơ chế ngôn ngữ:** `abstract class`, phương thức `abstract`, `interface`, `extends`, `implements`, override, phạm vi truy cập, kiểu tham chiếu, tính đa hình và phương thức `default`/`static`/`private` trong interface theo phiên bản.
- **Hợp đồng và thiết kế:** ranh giới giữa điều mã sử dụng được biết và điều hiện thực phải làm; tính thay thế giữa các implementation; khi chọn interface hoặc abstract class.
- **Java SE API làm ví dụ:** `Runnable`, `Comparable`, `Comparator`, `List`, `AbstractList`, `AutoCloseable` và cách đọc API docs để xác định hợp đồng chính xác.
- **Tương thích phiên bản:** cú pháp nào xuất hiện từ bản Java nào, cách kiểm tra compiler/runtime và cách biên dịch nhắm đến một Java release.

Những thứ **không cần để hiểu nền tảng này**: Spring DI/AOP, Hibernate, Gradle plugin, SDK của nhà cung cấp, giao thức của framework hoặc kiến trúc hệ thống lớn. Chúng có thể **dùng** interface và abstract class, nhưng quy tắc của các cấu trúc đó do ngôn ngữ Java quy định. Ví dụ, annotation `@Component` của Spring không quyết định xem `private` method trong interface có hợp lệ ở Java 8 hay không.

“Java Core” là tên gọi học tập phổ biến, **không phải tên một bản phát hành chính thức độc lập với Java SE**. Khi cần kết luận chính xác, phải gắn phát biểu với một **Java SE/JDK release cụ thể**, ví dụ Java 8, 17 hoặc 21.

## 2. Phân biệt Java SE, JDK, JVM, thư viện và framework

| Khái niệm | Dùng để làm gì? | Liên quan đến bài học |
| --- | --- | --- |
| Java language | Quy định cú pháp và ý nghĩa của `interface`, `abstract`, `sealed`, access modifier, override… | **Nguồn chuẩn** để xác minh cấu trúc nào được phép viết. |
| Java SE platform | Định nghĩa các API tiêu chuẩn và phần nền tảng cần thiết cho ứng dụng Java nói chung. | Cho ví dụ hợp đồng như `java.lang.Runnable`, `java.util.List`. |
| JDK (Java Development Kit) | Bộ công cụ phát triển, gồm compiler `javac`, launcher `java`, Javadoc, các công cụ khác cùng một bản triển khai nền tảng. | Dùng để **biên dịch/chạy/kiểm chứng** tính tương thích. |
| JVM | Thực thi bytecode và cung cấp cơ chế runtime, gồm nạp class và gọi phương thức động. | Giải thích vì sao lời gọi qua interface có thể chọn hiện thực lúc chạy. |
| Thư viện/framework bên ngoài | Cung cấp API bổ sung, ví dụ Spring, Jackson, JUnit. | Chỉ là **ngữ cảnh áp dụng**, không quyết định luật cú pháp Java Core. |

Cần tách **sự có mặt của một tính năng ngôn ngữ** khỏi **sự có mặt của một phương thức thư viện**. Chẳng hạn, từ Java 8 có cú pháp default method trong interface; nhưng một phương thức cụ thể của `List` hoặc `Comparator` phải được kiểm tra riêng ở trang Javadoc của **phiên bản API** đang dùng.

JDK và Java SE cũng không hoàn toàn là một: tài liệu API JDK còn có các công cụ/gói đặc thù cho JDK. Một API nằm trong một bản JDK không tự động đồng nghĩa nó thuộc hợp đồng API Java SE có thể dùng trên mọi triển khai nền tảng.

## 3. Các mốc phiên bản thực sự liên quan tới interface và abstraction

Bảng này liệt kê **mốc tính năng được chuẩn hóa**, thay vì cho rằng mọi Java đều có cú pháp như nhau.

| Java release | Thay đổi đáng chú ý | Tác động thực hành |
| --- | --- | --- |
| Java 7 trở về trước | Interface cơ bản có hợp đồng phương thức trừu tượng và hằng số; chưa có default/static method với thân trong interface. | Lớp triển khai phải cung cấp implementation cho phương thức abstract mà nó chưa thừa kế từ đâu. |
| **Java 8** | Interface hỗ trợ `default` và `static` methods; lambda và functional interface là phần quan trọng của lập trình Java 8. | Có thể cung cấp hành vi mặc định mà vẫn giữ hợp đồng; có thể truyền lambda nơi giao diện có đúng một phương thức abstract. |
| **Java 9** | Interface được phép có `private` instance/static methods. | Các default/static methods có thể chia sẻ logic nội bộ mà không công bố nó như API public. |
| Java 16 | `record` trở thành tính năng chính thức. | Dễ mô tả dữ liệu bất biến dạng shallow với thành phần khai báo; record có thể `implements` interface. Đây không phải thay thế cho mọi abstract class. |
| **Java 17** | `sealed class` và `sealed interface` trở thành tính năng chính thức. | Giới hạn có chủ đích những kiểu được trực tiếp `extends`/`implements` một abstraction. |

Những gì **ổn định xuyên suốt**: interface thể hiện một kiểu/hợp đồng; abstract class có thể chứa trạng thái và hành vi chung; lớp Java chỉ kế thừa trực tiếp một superclass nhưng có thể implement nhiều interface; phương thức override phải tuân thủ hợp đồng ngôn ngữ.

Khi học một API, **“Since: 8” ở trang Javadoc** cho biết mốc API đó xuất hiện; còn **JEP/trang Java Language Changes** cho biết trạng thái của một tính năng ngôn ngữ. Hai loại thông tin trả lời hai câu hỏi khác nhau.

### 3.1. Java 8: default và static methods trong interface

Tạo tệp **`CoreVersionDemo.java`**:

```java
public class CoreVersionDemo {
    interface Greeter {
        String name(); // public abstract ngầm định

        default String greet() {
            return "Hello, " + name();
        }

        static String topic() {
            return "Java Core";
        }
    }

    static final class Student implements Greeter {
        @Override
        public String name() {
            return "Lan";
        }
    }

    public static void main(String[] args) {
        Greeter greeter = new Student();
        System.out.println(greeter.greet());
        System.out.println(Greeter.topic());
    }
}
```

Nếu đang dùng **JDK 17** làm compiler:

```bash
javac --release 8 CoreVersionDemo.java
java CoreVersionDemo
```

Kết quả:

```text
Hello, Lan
Java Core
```

Giải thích: `name()` là hợp đồng abstract, `Student` phải triển khai nó; `greet()` là method mặc định dùng được qua một đối tượng `Greeter`; `topic()` được gọi qua **tên interface**. Với interface, `static` method không được kế thừa như instance method. `default` **không** có nghĩa “Java sẽ tự chọn cách xử lý mọi xung đột đa kế thừa”: khi hai interface không liên quan cung cấp default method cùng chữ ký, lớp triển khai thường phải tự giải quyết xung đột bằng override.

Vì mục tiêu của ví dụ là Java 8, không dùng `var`, `record`, `sealed` hay method private của interface trong cùng tệp.

### 3.2. Java 9: private helper method trong interface

Tạo tệp riêng **`InterfacePrivateDemo.java`**:

```java
import java.util.Locale;

public class InterfacePrivateDemo {
    interface Formatter {
        default String title(String value) {
            return normalized(value).toUpperCase(Locale.ROOT);
        }

        private String normalized(String value) {
            return value.trim();
        }
    }

    static final class BasicFormatter implements Formatter {
    }

    public static void main(String[] args) {
        Formatter formatter = new BasicFormatter();
        System.out.println(formatter.title("  java core  "));
    }
}
```

Biên dịch bằng JDK 17 với release 9 rồi chạy:

```bash
javac --release 9 InterfacePrivateDemo.java
java InterfacePrivateDemo
```

Kết quả:

```text
JAVA CORE
```

Nếu đổi thành `javac --release 8 InterfacePrivateDemo.java`, compiler **phải từ chối** vì Java 8 chưa hỗ trợ private method trong interface. Không phụ thuộc vào việc JDK 17 đang chạy có hiểu cú pháp mới: `--release 8` buộc việc kiểm tra theo tập quy tắc được hỗ trợ cho đích 8. Nội dung thông báo lỗi có thể khác giữa các phiên bản compiler.

Lưu ý: `private` trong interface dùng cho helper có thân, không phải cách khai báo một phương thức abstract để lớp triển khai bên ngoài override.

### 3.3. Java 17: giới hạn các implementation trực tiếp bằng sealed interface

Tạo tệp **`SealedDemo.java`**:

```java
public class SealedDemo {
    sealed interface Result permits Ok, Failed {
    }

    record Ok(String value) implements Result {
    }

    record Failed(String reason) implements Result {
    }

    public static void main(String[] args) {
        Result result = new Ok("done");
        System.out.println(result instanceof Ok);
    }
}
```

Biên dịch và chạy bằng JDK 17+ có hỗ trợ target 17:

```bash
javac --release 17 SealedDemo.java
java SealedDemo
```

Kết quả:

```text
true
```

Trong ví dụ này, `Result` giới hạn các **kiểu được trực tiếp implement** nó vào `Ok` và `Failed`. Hai `record` vốn là final nên đáp ứng quy tắc cho các nhánh được phép. Một class khác không thể tùy ý `implements Result`. Cần phân biệt phạm vi của `sealed`: nó kiểm soát quan hệ mở rộng kiểu, **không tự bảo đảm** validation dữ liệu, bảo mật hay tính bất biến sâu của mọi đối tượng.

Code `record` và `sealed` không biên dịch khi target là `--release 8` hoặc `--release 11`. Nếu gặp ví dụ dùng `sealed` trong JDK 15/16, đó là giai đoạn **preview**, cần xem đúng trạng thái của bản phát hành đó; ở Java 17, `sealed` đã là tính năng chuẩn, không cần `--enable-preview`.

## 4. Chọn tài liệu nào để đối chiếu?

Khi có mâu thuẫn giữa bài blog, IDE và đoạn code, nên tra cứu theo thứ tự câu hỏi cần giải:

| Câu hỏi | Nguồn nên mở | Cách đọc |
| --- | --- | --- |
| “Cú pháp này hợp lệ từ Java mấy?” | **Java Language Changes** và **Java Language Specification (JLS)** theo release | Xác định từ khóa, modifier, giới hạn ngôn ngữ, trạng thái final/preview. |
| “`List` hoặc `Comparator` có method này từ khi nào?” | **Javadoc API theo đúng phiên bản**, trang class/interface cụ thể | Kiểm tra chữ ký, `Since`, `default`/`static`, điều kiện lỗi và `@Deprecated`. |
| “Tính năng từng preview hay đã ổn định?” | **JEP** liên quan và release notes | So sánh trạng thái đề xuất, preview/incubator, final và thay đổi qua mỗi lần phát hành. |
| “Bản JDK nào có thể compile/chạy code?” | Tài liệu `javac`, `java`, và output thực tế của công cụ | Kiểm tra JDK đang chọn, `--release`, classpath/module path và runtime. |
| “Nên chọn JDK nào cho dự án dài hạn?” | Release/support roadmap của đúng nhà phân phối JDK | Phân biệt bản feature release với LTS, thời hạn hỗ trợ và giấy phép riêng của nhà cung cấp. |

Các địa chỉ **chính thức** hữu ích:

1. [Java Language Changes – Java 17](https://docs.oracle.com/en/java/javase/17/language/java-language-changes-release.html) — mốc ngôn ngữ; có các phần `sealed` và `record`.
2. [JLS Java SE 17](https://docs.oracle.com/javase/specs/jls/se17/html/index.html) — quy tắc ngôn ngữ chính thức; tra mục về Interfaces, Classes, Method Declarations.
3. [Java SE 17 & JDK 17 API Specification](https://docs.oracle.com/en/java/javase/17/docs/api/index.html) — tra chữ ký từng API, package/module, `Since`, `@Deprecated`.
4. [`javac` JDK 17](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html) — các lựa chọn `--release`, `--source`, `--target`.
5. [JEP 409: Sealed Classes](https://openjdk.org/jeps/409) — lịch sử và trạng thái của sealed types.
6. [Oracle Java SE Support Roadmap](https://www.oracle.com/java/technologies/java-se-support-roadmap.html) — lịch phát hành và phân loại LTS.
7. [JDK 27 Release Notes (15/09/2026)](https://www.oracle.com/java/technologies/javase/27all-relnotes.html) — ví dụ về trang ghi nhận thay đổi ở một release mới hơn Java 17.

Mỗi tài liệu có **phiên bản** riêng. Đừng đọc Javadoc của Java 21 rồi khẳng định API đó tồn tại trong Java 8, hoặc dùng JLS Java 17 để suy ra cú pháp Java 8. Đối với tutorial cũ của Oracle, đọc cảnh báo phiên bản nếu tài liệu nói nó viết cho JDK 8.

**Mốc thời gian cần ghi rõ khi so sánh “mới nhất”:** tính đến **23/10/2026**, JDK 27 là feature release đã phát hành tháng 9/2026, còn JDK 25 là bản LTS mới nhất của Oracle trong danh sách công bố. `LTS` là chính sách hỗ trợ phát hành, **không** là cú pháp hay hệ loại `interface`. Khi đọc bài học ở thời điểm sau đó, hãy kiểm tra lại roadmap thay vì mặc định con số này còn đúng.

## 5. Cách xác minh Java/JDK thực tế trên máy

### Bước 1: xem compiler và runtime đang được gọi

Mở terminal trong thư mục dự án và chạy:

```bash
java -version
javac -version
```

Hai lệnh cần được kiểm tra **riêng**, vì hệ thống có thể trỏ `java` và `javac` đến hai bản JDK khác nhau tùy cấu hình `PATH`, `JAVA_HOME`, IDE hoặc toolchain của build. `java -version` hiển thị runtime; `javac -version` hiển thị compiler. Không thể suy ra JDK build thực tế chỉ từ giao diện “Project SDK” nếu build dùng toolchain khác.

Nếu `javac` không tồn tại nhưng `java` chạy được, có thể môi trường đang chỉ có runtime hoặc `PATH` chưa trỏ đúng thư mục công cụ của JDK. Hãy kiểm tra cài đặt JDK và cấu hình shell.

### Bước 2: chọn phiên bản đích, không mặc định lấy phiên bản compiler

Với một JDK hỗ trợ Java 8/9/17, dùng các lệnh:

```bash
javac --release 8 CoreVersionDemo.java
javac --release 9 InterfacePrivateDemo.java
javac --release 17 SealedDemo.java
```

**`--release N`** hướng compiler kiểm tra cú pháp theo Java N, tạo class file cho phiên bản đó và biên dịch với tập API nền tảng mà bản N công bố. Đây là lựa chọn nên ưu tiên khi muốn kiểm tra khả năng dùng Java N.

Đừng nhầm:

- `--source N` giới hạn **cú pháp ngôn ngữ**, nhưng đứng một mình không chứng minh rằng code chỉ dùng API có trong Java N.
- `--target N` chọn **định dạng bytecode đích**, cũng không đủ để hạn chế API theo Java N nếu cấu hình sai.
- `--release N` kết hợp các mặt trên với kiểm tra API nền tảng của release N. Không ghép `--release` với `--source` hoặc `--target` trong cùng một lệnh.

`javac` chỉ hỗ trợ một **tập hữu hạn các release đích**; `javac --help` của chính bản JDK đang dùng cho biết danh sách được hỗ trợ. JDK mới **không nhất thiết** còn hỗ trợ biên dịch cho mọi release rất cũ.

### Bước 3: kiểm tra runtime đích

Biên dịch thành công bằng `--release 17` **không** đồng nghĩa có thể chạy file `.class` bằng Java 8. Runtime phải hỗ trợ định dạng class file và các tính năng/API mà chương trình cần; hướng chạy thông thường là dùng một runtime cùng hoặc mới hơn bản đích và kiểm tra phụ thuộc thực tế.

Ví dụ, khi `SealedDemo.java` được biên dịch với `--release 17`, hãy chạy bằng runtime Java 17+:

```bash
java SealedDemo
```

Nếu gặp `UnsupportedClassVersionError`, kiểm tra lại output của `java -version`, phiên bản biên dịch và vị trí class file đang được nạp. Nếu gặp `NoSuchMethodError` hoặc `ClassNotFoundException`, còn phải xem sự khác biệt API và dependency/runtime classpath; chỉ đổi `--target` không đủ để bảo đảm tương thích.

### Bước 4: với công cụ build, đối chiếu phiên bản ở cả ba nơi

Trong dự án dùng Maven/Gradle/IDE, hãy xác định:

1. **JDK chạy build/compiler**: bản `javac` hoặc Java toolchain được chọn.
2. **Release biên dịch đích**: cấu hình `release` của compiler; với dự án Gradle có thể là `options.release`, với Maven là `maven.compiler.release`.
3. **JDK chạy ứng dụng**: bản `java` tại môi trường chạy hoặc container.

Một project có thể chạy build trên JDK 21 nhưng xuất bytecode hướng Java 17 nếu compiler hỗ trợ `--release 17`. Điều đó không làm cú pháp Java 21 tự nhiên hợp lệ trong các tệp được biên dịch cho Java 17.

## 6. Quy trình đối chiếu một khẳng định cụ thể

Giả sử thấy câu: “Trong Java, interface có thể khai báo private method”. Cách kiểm chứng chặt chẽ là:

1. **Chuyển thành câu hỏi có phiên bản:** “Trong **Java 8** có thể khai báo private instance method trong interface không? Còn **Java 9**?”
2. **Tra nguồn ngôn ngữ:** trang *Java Language Changes* ghi mốc private interface methods là Java 9.
3. **Viết mẫu nhỏ nhất có thể biên dịch:** dùng `InterfacePrivateDemo.java` ở trên, tách biệt với framework.
4. **Biên dịch hai mục tiêu bằng cùng một JDK phù hợp:** `--release 8` sẽ bị từ chối; `--release 9` hợp lệ.
5. **Kết luận đúng phạm vi:** “Private helper method trong interface được hỗ trợ từ Java 9”; không mở rộng thành “mọi interface method có thể là private abstract” hoặc “Java 8 cũng hỗ trợ vì đang cài JDK 17”.

Tương tự, với phát biểu “interface có thể cài sẵn method”, cần hỏi method loại nào: `default`/ `static` từ Java 8; `private` helper từ Java 9. Với “`sealed interface` có dùng được không?”, phải hỏi Java 15/16 đang preview hay Java 17 trở lên là tính năng chuẩn.

Khi nguồn bất đồng, hãy ghi lại đủ **phiên bản Java**, **đường dẫn tài liệu**, **lệnh javac**, **đầu vào tối thiểu** và **kết quả quan sát được**. Một video hoặc blog không nêu phiên bản không đủ để bác bỏ compiler và đặc tả đúng phiên bản.

## 7. Giới hạn quan trọng và lỗi thường gặp

- **Không nhầm từ khóa với thư viện.** `abstract`/`interface` là ngôn ngữ; `List`/`Comparator` là API; Spring là framework. Mỗi loại cần nguồn đối chiếu phù hợp.
- **Không dùng JDK mới để suy ra JDK cũ.** Chương trình chạy trên Java 17 với cú pháp record/sealed không chứng minh nó chạy hoặc biên dịch cho Java 8.
- **Không đồng nhất JDK và Java SE spec.** Một số công cụ và API cụ thể thuộc JDK, không phải cam kết Java SE chung. Đừng phụ thuộc vào API nội bộ chỉ vì compiler trên máy tình cờ thấy được chúng.
- **Không hiểu sai `default` method là “không cần implementation”.** `default` có implementation ngay trong interface nhưng vẫn chịu quy tắc override, phân giải xung đột và quyền truy cập.
- **Không đồng nhất LTS và độ mới tính năng.** LTS liên quan tới chính sách hỗ trợ; một non-LTS mới hơn có thể bổ sung tính năng nhưng không thích hợp với mọi chiến lược vận hành.
- **Không bỏ qua preview feature.** Một tính năng ở trạng thái preview có thể cần cờ compile/run cụ thể và có thể đổi trước khi thành chính thức. Không lấy ví dụ preview để trình bày như cú pháp phổ quát của Java SE.
- **Không để API docs của phiên bản mới che mất `Since` và `Deprecated`.** Một method có thể chưa tồn tại, đổi trạng thái hoặc bị loại bỏ ở bản mục tiêu.
- **Không gán kết quả thử nghiệm cho mọi môi trường.** Một ví dụ độc lập kiểm tra cú pháp; build thực tế còn phụ thuộc module path, classpath, annotation processor, công cụ build và runtime đích.

## 8. Checklist áp dụng cho từng bài abstract/interface về sau

Trước khi đọc hoặc viết một ví dụ, tự xác nhận:

- Đây là **quy tắc ngôn ngữ Java** hay **API của một thư viện**?
- Bài dùng Java **phiên bản nào**; tính năng xuất hiện từ release nào; đang final hay preview?
- Compiler có đang dùng **đúng `--release`**; bản JDK có hỗ trợ release đó?
- Runtime thực thi có cùng khả năng với binary đã biên dịch và API cần dùng?
- Ví dụ minh họa abstraction có yêu cầu **thư viện bên ngoài** không? Nếu có, cần tách quy tắc Java Core khỏi hành vi thư viện đó.
- Kết luận đã dựa trên **JLS/Javadoc/JEP/release notes** đúng phiên bản và một ví dụ tối thiểu tái hiện được chưa?

**Tự luyện:** Hãy thử biên dịch ba tệp `CoreVersionDemo.java`, `InterfacePrivateDemo.java`, `SealedDemo.java` bằng JDK 17 với `--release 8`, `--release 9` và `--release 17` tương ứng. Sau đó cố tình giảm `--release` của hai tệp sau và giải thích vì sao compiler từ chối. Đối chiếu kết luận với Java Language Changes, không dựa vào việc IDE có tô màu cú pháp hay không.

**Ghi nhớ:** trong Java Core, cú pháp và hợp đồng abstraction/interface do **phiên bản ngôn ngữ** quyết định; API nền tảng do **phiên bản Java SE** quy định; `javac --release` cùng môi trường runtime giúp biến lời khẳng định thành điều có thể kiểm chứng. Luôn nói rõ phiên bản trước khi kết luận một tính năng “có” hoặc “không”.
