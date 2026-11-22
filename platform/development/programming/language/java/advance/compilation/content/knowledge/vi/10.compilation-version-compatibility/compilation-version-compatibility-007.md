# Bật preview khi biên dịch và chạy trên phiên bản Java tương ứng

Java thường phát hành những khả năng ngôn ngữ, JVM hoặc API dưới trạng thái **preview** trước khi quyết định đưa chúng thành tính năng ổn định. Preview không đồng nghĩa với một bản Java “beta” không hoàn chỉnh: khả năng đó được đặc tả và triển khai để lập trình viên thử nghiệm, nhưng **chưa cam kết giữ nguyên trong các bản Java tương lai**. Để dùng preview đúng cách, phải đồng bộ **JDK biên dịch**, **mức source/release**, **cờ compiler** và **JDK/cờ khi chạy**.

Bài thuộc nhóm **Tương thích phiên bản** của Java Advance – compilation. Trọng tâm là các lệnh `javac` và `java`, tình huống sai phiên bản, dấu hiệu class file được biên dịch bằng preview, và chiến lược kiểm thử/chuyển đổi khi preview thay đổi hoặc được chuẩn hóa. Ví dụ thực thi dùng **JDK 24** với tính năng *module import declarations* ở trạng thái **second preview trong Java 24**. Đây là ví dụ gắn với đúng phiên bản: ở Java 25, tính năng module import declarations đã được chuẩn hóa; không được suy diễn rằng chính nó vẫn là preview trong mọi JDK mới hơn.

## 1. Preview feature là gì?

Một preview feature là khả năng đang được Java SE cung cấp để thu thập kinh nghiệm thực tế trước khi chốt lâu dài. Những trạng thái có thể xảy ra giữa các bản phát hành:

1. **First preview:** tính năng xuất hiện lần đầu theo một JEP xác định.
2. **Second/third/... preview:** tiếp tục được thử nghiệm; tên, cú pháp hoặc ngữ nghĩa có thể thay đổi.
3. **Final/permanent:** tính năng được chấp nhận là một phần ổn định của phiên bản Java đó.
4. **Removed:** tính năng có thể bị loại bỏ thay vì trở thành tiêu chuẩn.

Có nhiều nhóm preview cần phân biệt:

- **Preview language feature:** cú pháp hoặc quy tắc ngôn ngữ mới, chẳng hạn một cấu trúc `import` mới. `javac` phải nhận diện nguồn dùng tính năng đó.
- **Preview VM feature:** thay đổi khả năng của nền tảng thực thi theo đặc tả tương ứng. Một chương trình phụ thuộc vào preview VM feature có các yêu cầu runtime tương ứng.
- **Preview API:** class/interface/method mới trong các namespace API nền tảng được đánh dấu preview. API preview có thể cần cờ khi biên dịch hoặc thực thi ngay cả khi cú pháp của nguồn trông quen thuộc.
- **Incubator API/module:** cơ chế thử nghiệm API qua incubator module, **khác** preview. Các cờ như `--add-modules` có thể tham gia, không được mặc định coi `--enable-preview` là cách kích hoạt mọi incubator module.

Tương tự, **experimental VM options**, **early-access JDK**, **internal JDK APIs** hoặc những tính năng *foreign function/native access* có quy tắc riêng không nên tự động gọi là preview language feature. Phải xem tài liệu/JEP của **đúng phiên bản** và **đúng tính năng**.

**Điểm cần nhớ:** “Có trên JDK mới” không có nghĩa “đã final”; “đã preview ở Java 24” cũng không có nghĩa “cần bật preview ở Java 25”. Trạng thái thuộc về **tính năng ở một bản phát hành cụ thể**.

## 2. Quy tắc quan trọng nhất: compiler và runtime phải cùng release preview

Giả sử phiên bản dùng để thử là **Java N**. Khi biên dịch nguồn dùng preview của Java N, dùng chính **`javac` thuộc JDK N** và bật:

~~~sh
javac --enable-preview --release N MyProgram.java
~~~

Trong đó `N` là số phiên bản thực, chẳng hạn `24` trong bài này; dòng trên chỉ minh họa cú pháp, **không phải lệnh có thể chạy nguyên văn**. Cũng có thể dùng `-source N` với `--enable-preview`, nhưng `--release N` thường hữu ích hơn vì còn giới hạn API nền tảng theo release được chọn.

Khi chạy bytecode phụ thuộc preview của Java N:

~~~sh
java --enable-preview MyProgram
~~~

`java` ở đây phải là **runtime hỗ trợ preview của Java N**, thường là JDK/JRE của **chính Java N**. Cờ `--enable-preview` không chuyển một JVM đời khác thành JVM của Java N và không đưa trở lại cú pháp/API đã bị thay đổi.

| Thành phần | Điều cần kiểm tra |
|---|---|
| `javac` | `javac -version` thực sự báo phiên bản **N** |
| Language level | `--release N` hoặc `-source N` cùng `--enable-preview` |
| Source code | Tính năng được dùng đúng theo bản preview của **N** |
| Class files | Bytecode mang version tương ứng với **N**; lớp thực sự dùng preview language/VM có marker preview |
| `java` | `java -version` cùng phiên bản **N** và truyền `--enable-preview` |
| Thư viện | Binary/API và classpath/module path tương thích với runtime được chọn |

Không dùng một `javac` đời mới để “biên dịch preview của bản cũ” bằng cách đơn giản đặt `--release <bản cũ>`. Ví dụ, trên JDK 24, `javac --enable-preview --release 17 ...` **bị từ chối**, dù Java 17 từng có các preview riêng. Compiler JDK 24 chỉ hỗ trợ **preview của chính Java 24** khi bật tùy chọn đó.

### 2.1. Khác biệt giữa --release và --source

- `--source 24`: chọn quy tắc ngôn ngữ của release 24 trong ngữ cảnh compiler hỗ trợ, nhưng không tự giới hạn API nền tảng mà trình biên dịch đang dùng giống `--release`.
- `--release 24`: chọn ngôn ngữ **và** API Java SE phù hợp release 24, nên có lợi khi tránh vô tình dùng API mới hơn phiên bản nhắm tới.
- `--enable-preview`: bật việc sử dụng preview của **release hiện tại của javac**, phối hợp với `--source` hoặc `--release`.

Cờ `--release` không tự bật preview. Lệnh `javac --release 24` vẫn từ chối cú pháp preview Java 24 nếu không có `--enable-preview`.

Đối với dự án **không** cần preview, thường **không nên bật preview theo thói quen**. Nó khiến cấu hình build phức tạp hơn và dễ vô tình đưa preview vào một nhánh mã vốn yêu cầu ổn định.

## 3. Ví dụ Java 24: module import declarations (second preview)

Trong Java 24, khai báo:

~~~java
import module java.base;
~~~

là một **preview language feature** theo JEP 494. Nó cho phép import các kiểu thuộc những package được module tương ứng export, giúp mã nguồn ngắn hơn trong một số ngữ cảnh. Nó **không** có nghĩa chương trình của bạn phải khai báo một `module-info.java` riêng; ví dụ dưới đây là class thông thường trong unnamed module.

Trạng thái theo release phải được ghi rõ:

| Phiên bản | Trạng thái module import declarations |
|---|---|
| Java 23 | First preview (JEP 476) |
| Java 24 | Second preview (JEP 494) |
| Java 25 | Final/permanent (JEP 511) |

Trong phạm vi bài này ta cố ý dùng **JDK 24**, vì ở release đó cần hai cờ preview để biên dịch và chạy chương trình mẫu. Nếu học bằng JDK 25 trở lên, hãy dùng tài liệu của đúng JDK đó: **không dùng trạng thái preview của Java 24 để suy đoán cú pháp/cờ bắt buộc ở Java 25**.

### 3.1. Tạo tệp PreviewExample.java

Tạo một thư mục trống dành riêng cho bài thử. Trong thư mục đó, tạo **`PreviewExample.java`** với nội dung đầy đủ:

~~~java
import module java.base;

public class PreviewExample {
    public static void main(String[] args) {
        List<String> names = List.of("Lan", "Mai");
        System.out.println(names.get(0));
        System.out.println(names.size());
    }
}
~~~

Vì `java.base` export `java.util`, compiler nhận ra `List` mà không cần `import java.util.List;` tường minh. `List.of` là API đã ổn định từ các phiên bản Java trước; **điểm preview trong ví dụ chỉ là cú pháp `import module`**.

Tên tệp phải khớp class công khai `PreviewExample`; không có `package`, nên thao tác có thể thực hiện trực tiếp từ thư mục chứa nguồn.

### 3.2. Kiểm tra công cụ

Từ terminal:

~~~sh
javac -version
java -version
~~~

Trong môi trường đã dùng để kiểm chứng, hai lệnh đều báo JDK/JVM 24.0.2. Nếu một lệnh báo Java 17, 21, 25 hoặc bản khác, **đừng chạy y hệt ví dụ với kỳ vọng giống kết quả**; chọn đúng JDK 24 hoặc thay ví dụ/cờ theo preview của release đang có.

Đối với dự án thực tế, `JAVA_HOME`, `PATH`, IDE Project SDK và Java toolchain trong Gradle/Maven có thể chọn các JDK khác nhau. `JAVA_HOME` chỉ là quy ước của môi trường/tooling; đặt nó không bảo đảm shell đang dùng compiler như mong đợi. Cần kiểm tra cả `javac -version` và `java -version`.

### 3.3. Biên dịch không bật preview: dự kiến lỗi

Khi dùng `javac` từ JDK 24, thử:

~~~sh
javac --release 24 -encoding UTF-8 PreviewExample.java
~~~

Lệnh **thất bại**. Nội dung chẩn đoán quan trọng:

~~~text
error: module imports are a preview feature and are disabled by default.
~~~

Compiler hiểu cấu trúc `import module` thuộc preview của Java 24 nhưng không cho sử dụng mặc định. Không phải lỗi `List` không tồn tại, không phải lỗi classpath; cần bật **preview ở giai đoạn biên dịch**.

### 3.4. Biên dịch đúng cho JDK 24

Chạy:

~~~sh
javac --enable-preview --release 24 -encoding UTF-8 PreviewExample.java
~~~

Lệnh **thành công**, tạo `PreviewExample.class`. Với javac 24.0.2, còn có ghi chú dạng:

~~~text
Note: PreviewExample.java uses preview features of Java SE 24.
Note: Recompile with -Xlint:preview for details.
~~~

Đây là **note**, không phải dấu hiệu biên dịch thất bại. Có thể thêm `-Xlint:preview` để xem cảnh báo chi tiết hơn:

~~~sh
javac -Xlint:preview --enable-preview --release 24 -encoding UTF-8 PreviewExample.java
~~~

Khi kiểm chứng bằng JDK 24, compiler đưa ra cảnh báo liên quan module import preview. Với một số cấu hình compiler/JDK, văn bản note/warning có thể khác; yếu tố chính là **exit code 0** cùng class file đã tạo.

Một cú pháp khác cũng được JDK 24 chấp nhận cho ví dụ là:

~~~sh
javac --enable-preview -source 24 -encoding UTF-8 PreviewExample.java
~~~

Tuy nhiên, với quy trình yêu cầu quản lý **tính tương thích cả ngôn ngữ và API**, nên ưu tiên `--release 24`.

### 3.5. Chạy thiếu cờ preview: dự kiến lỗi

Sau khi đã biên dịch thành công với preview, thử:

~~~sh
java -cp . PreviewExample
~~~

Lệnh **không chạy được** trên JDK 24. JVM từ chối class file dùng preview, với nội dung quan trọng:

~~~text
java.lang.UnsupportedClassVersionError: Preview features are not enabled
~~~

Đây là lỗi **runtime**, khác với lỗi compiler ở mục 3.3. Cờ preview dùng trong câu lệnh `javac` đã hoàn thành nhiệm vụ của lần biên dịch; nó **không tự truyền** cho câu lệnh `java` tiếp theo.

### 3.6. Chạy đúng trên Java 24

Dùng runtime Java 24:

~~~sh
java --enable-preview -cp . PreviewExample
~~~

**Stdout chính xác đã kiểm chứng**:

~~~text
Lan
2
~~~

Tại thời điểm này, đã đồng bộ đủ:

1. JDK biên dịch 24.
2. `--enable-preview --release 24` cho `javac`.
3. Bytecode chứa preview Java 24.
4. JVM 24 với `--enable-preview` khi chạy.

Nếu build tool tạo JAR, không nên nghĩ cờ preview nằm mãi trong JAR manifest; cấu hình của **tiến trình JVM đang khởi chạy** mới quyết định preview có được bật hay không.

## 4. Class file preview: major version và minor version

Từ mô hình class file hiện đại của Java, mỗi `.class` có **major** và **minor version** trong header. Một class file **thực sự phụ thuộc vào preview language/VM feature của Java 24** có thể được nhận diện bằng:

~~~text
minor version: 65535
major version: 68
~~~

Số major **68** tương ứng với Java 24, trong khi minor **65535** được dùng để đánh dấu class file phụ thuộc preview language/VM feature theo cơ chế đặc tả. JVM sẽ không xem nó như một class Java 24 ổn định thông thường.

Kiểm tra:

~~~sh
javap -verbose PreviewExample.class
~~~

Trong output, tìm `minor version:` và `major version:`. Với `PreviewExample.java` dùng module import preview ở phần 3, hai giá trị trên **đã được kiểm chứng thực tế**.

### 4.1. Bật --enable-preview không đồng nghĩa mọi class đều mang minor 65535

Giả sử tệp **`StableExample.java`** có nội dung:

~~~java
public class StableExample {
    public static void main(String[] args) {
        System.out.println("stable");
    }
}
~~~

Biên dịch trên JDK 24 bằng:

~~~sh
javac --enable-preview --release 24 StableExample.java
javap -verbose StableExample.class
~~~

Kết quả kiểm chứng:

~~~text
minor version: 0
major version: 68
~~~

Chạy **không** có `--enable-preview` vẫn thành công:

~~~sh
java StableExample
~~~

Stdout:

~~~text
stable
~~~

**Giải thích:** compiler được phép sử dụng preview trong lượt build, nhưng chính `StableExample` không sử dụng preview language/VM feature cần marker class file. Vì vậy không thể nhìn cờ build rồi khẳng định **mọi class** trong artifact đều yêu cầu cờ preview khi JVM chạy. Cần đánh giá **bytecode thực tế** và các API/chức năng được gọi.

Ngược lại, nếu một lớp có marker preview của Java 24, chạy trên JVM 24 thiếu cờ sẽ thất bại. Một JVM khác release không nhất thiết hỗ trợ preview class file này, ngay cả khi JVM đó có cờ cùng tên.

### 4.2. Vì sao không thể coi preview class file là portable như class thường?

Bản preview có thể đổi quy tắc ngôn ngữ/VM ở lần phát hành kế tiếp. Class file preview được ràng buộc với **release tạo ra nó**. Cờ `--enable-preview` của một runtime mới **không được hiểu** là hứa hỗ trợ các class file preview của mọi bản Java cũ.

Vì thế, khi nâng JDK, **phải biên dịch lại từ nguồn** và kiểm thử trên release mới. Nếu tính năng đã được final, có thể loại bỏ cờ preview sau khi xác nhận source/API được hỗ trợ ở release đích. Nếu tính năng vẫn preview nhưng cú pháp đổi, cần cập nhật source theo JEP mới rồi biên dịch lại.

Đừng xóa marker class file hoặc sửa major/minor bằng tay để “qua” kiểm tra JVM; đó không phải cách chuyển đổi an toàn và không đảm bảo ngữ nghĩa bytecode tương thích.

## 5. Trường hợp --enable-preview dùng sai phiên bản

Một lỗi phổ biến là cài JDK 24 rồi muốn thử preview từng có trong Java 17 bằng lệnh:

~~~sh
javac --enable-preview --release 17 SomeSource.java
~~~

Trên **javac 24**, lệnh bị từ chối **trước khi** xem nguồn dùng preview gì, với thông điệp quan trọng:

~~~text
error: invalid source release 17 with --enable-preview
(preview language features are only supported for release 24)
~~~

Điều đó không có nghĩa Java 17 “không có preview”. Nó chỉ có nghĩa **JDK 24 compiler không cung cấp chế độ preview của Java 17**. Nếu muốn tái lập một tính năng preview theo đúng thiết kế Java 17, hãy chọn **JDK 17** để biên dịch và chạy với các cờ phù hợp, rồi xem JEP ở thời điểm đó.

Tương tự, trên javac 24:

~~~sh
javac --enable-preview --source 23 SomeSource.java
~~~

cũng không phải cách dùng preview của Java 23. `--source` có thể chọn ngôn ngữ ổn định của release trước, nhưng `--enable-preview` áp dụng preview của **current release của javac**, không phải preview lịch sử.

### 5.1. Ví dụ cấu hình đúng/sai với JDK 24

| Lệnh hoặc tổ hợp | Với ví dụ PreviewExample.java ở Java 24 |
|---|---|
| `javac --release 24 PreviewExample.java` | Sai: preview đang tắt |
| `javac --enable-preview --release 24 PreviewExample.java` | Đúng: tạo class preview |
| `javac --enable-preview -source 24 PreviewExample.java` | Hợp lệ về source level/preview của JDK 24 |
| `javac --enable-preview --release 17 PreviewExample.java` | Sai: javac 24 chỉ cho preview của release 24 |
| `java PreviewExample` | Sai: class preview Java 24 bị JVM 24 từ chối khi chưa bật |
| `java --enable-preview PreviewExample` | Đúng với runtime Java 24, trong môi trường classpath phù hợp |

Bảng này **không phải** hướng dẫn cho JDK 25 hay 26. Số phiên bản là một phần của hợp đồng thử nghiệm và phải thay đổi cùng với feature status theo release.

## 6. Phân biệt phiên bản runtime với đích biên dịch

Trong dự án cần chạy Java 17 trên production nhưng lập trình viên sử dụng JDK 24, có thể viết mã Java 17 **ổn định** và biên dịch:

~~~sh
javac --release 17 -encoding UTF-8 StableExample.java
~~~

Dùng JDK 24 compiler nhưng target class file/API Java 17 được hỗ trợ. Chương trình ổn định như vậy có thể được triển khai trên Java 17 khi các dependency cũng tương thích và môi trường chạy đáp ứng yêu cầu.

**Không thể áp suy luận đó trực tiếp cho preview.** Preview không phải tập khả năng bất biến xuyên release. Muốn dùng preview Java 24 thì target Java 24; không thể vừa yêu cầu preview Java 24 vừa nhắm runtime Java 17 bằng `--release 17`.

Cần phân biệt ba trường hợp:

1. **Ổn định và backwards-targeted:** có thể dùng JDK mới biên dịch mã cho bản Java cũ nhờ `--release` tương ứng.
2. **Preview của release hiện tại:** compiler và runtime được chọn đúng bản đang có preview; cả hai giai đoạn bật flag.
3. **Preview đã được final ở bản mới:** có thể nâng nguồn/build để dùng trạng thái final và bỏ preview flag, nhưng phải kiểm tra các thay đổi API/cú pháp và biên dịch lại.

Ví dụ module import declarations đã **final tại Java 25**. Đây là lý do bài không phát biểu “mọi Java dùng `import module` luôn phải bật preview”; yêu cầu đó chính xác cho **bài thử Java 24**, không phải một quy tắc bất biến.

## 7. Preview API có gì khác với preview syntax?

Từ góc nhìn người học, một source file có thể **không chứa cú pháp lạ** nhưng vẫn gọi API được Java đánh dấu là preview. Ví dụ minh họa khái niệm:

~~~java
// Mã giả về một API preview nào đó: không phải chương trình chạy độc lập.
// somePreviewApi.operation();
~~~

Trường hợp này cần kiểm tra tài liệu của chính API ở **JDK đang sử dụng**. Tùy đặc điểm API và cách nó được khai báo, việc dùng nó có thể được `javac` chẩn đoán/cảnh báo nếu preview chưa bật; quá trình thực thi cũng có những giới hạn preview tương ứng.

Không nên suy ra việc cần flag chỉ bằng cách nhìn nguồn có từ khóa mới hay không. Ngược lại, **một API thử nghiệm không phải preview** có thể có quy tắc bật module hoặc cờ riêng. Phải đọc JEP, javadoc và mô tả option tương ứng release.

Nguyên tắc thực hành:

- Phân biệt **preview language/VM feature**, **preview API**, **incubator module** và **experimental runtime option**.
- Ghi rõ tên JEP và release mà API/cú pháp đang là preview.
- Test compiler với đúng flags, xem diagnostics; test runtime thật với cùng release.
- Với thư viện công khai, cân nhắc việc phơi lộ preview type trong public API vì nó có thể buộc downstream consumers dùng cùng release/flags.

## 8. Tính tương thích với các build tool

Trong dự án thực tế, lệnh do bạn gõ bằng tay chỉ là một phần. IDE, Gradle, Maven hoặc CI có thể chạy **compiler JDK khác** với terminal hoặc JVM chạy test khác với JVM chạy ứng dụng. Vì preview cần hai phía, hãy cấu hình và kiểm tra chúng **riêng biệt**.

### 8.1. Gradle: compiler và test/run process là hai cấu hình

Một cấu hình Groovy DSL **minh họa** dùng Java toolchain 24:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(24)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['--enable-preview']
    options.release = 24
}

tasks.withType(Test).configureEach {
    jvmArgs += ['--enable-preview']
}

tasks.withType(JavaExec).configureEach {
    jvmArgs += ['--enable-preview']
}
~~~

Đây là minh họa phần cấu hình preview; muốn chạy ứng dụng `application`, còn phải cấu hình main class/source sets/dependencies phù hợp. Phiên bản Gradle phải hỗ trợ JDK 24/toolchain; không phải mọi Gradle cũ đều chạy được với JDK mới. Đừng coi snippet này là một project Gradle hoàn chỉnh.

Vì sao cần ba phần?

- `JavaCompile` chạy `javac`, cần bật preview khi xử lý nguồn.
- `Test` chạy test JVM riêng, cần bật preview nếu test nạp các class preview.
- `JavaExec` chạy chương trình bằng JVM riêng, nên cũng cần flag khi dùng preview.

Khi đóng gói và triển khai bằng một cơ chế JVM khác, ví dụ `java -jar` bên ngoài Gradle, phải bảo đảm command launch đó cũng có `--enable-preview`.

### 8.2. Maven: thuộc tính release và plugin/compiler args

Ví dụ định hướng trong `pom.xml` (đây là **đoạn cấu hình**, không phải POM tự chạy):

~~~xml
<properties>
    <maven.compiler.release>24</maven.compiler.release>
</properties>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <configuration>
                <compilerArgs>
                    <arg>--enable-preview</arg>
                </compilerArgs>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Ở test, các plugin Surefire/Failsafe chạy JVM và cần cấu hình **argLine**/JVM args phù hợp, ví dụ `--enable-preview` khi test cần nạp class preview. Chi tiết cách các plugin kế thừa args, cách Java toolchain được chọn và version hỗ trợ phụ thuộc bản Maven/plugin; cần đọc tài liệu và lệnh chạy thực tế.

Không chỉ thêm `--enable-preview` vào compilerArgs rồi tuyên bố mọi test/build/runtime đã được bật. Với CI, hãy kiểm tra cả `mvn -version` và lệnh JVM của test/packaging.

### 8.3. IDE và CI

Trong IDE, hãy xác minh đồng thời:

1. Project/module SDK là JDK của release preview mục tiêu.
2. Language level bật preview tương ứng.
3. Compiler options có `--enable-preview` khi cấu hình IDE không tự thêm đúng cờ.
4. Run/Debug configuration có JVM argument `--enable-preview`.
5. Test runner và terminal tích hợp không chạy nhầm JDK khác.
6. CI dùng cùng JDK release và nguồn/dependency/configuration, không chỉ cùng tên branch.

Với IntelliJ IDEA, Eclipse hoặc VS Code, vị trí UI setting cụ thể thay đổi theo phiên bản; nguyên tắc là **compiler level** và **runtime arguments** phải đồng bộ. Không sửa lỗi preview bằng cách thêm đại một JAR hoặc mở module access; các lỗi đó thuộc cơ chế khác.

## 9. Preview trong dependency và artifact được phát hành

Preview có thể xuất hiện không chỉ ở module ứng dụng mà còn trong một **JAR thư viện phụ thuộc**. Khi biên dịch ứng dụng với thư viện chứa class file preview, bạn có thể gặp chẩn đoán từ compiler hoặc vấn đề tương thích release; khi chạy, JVM vẫn phải xử lý class file phụ thuộc preview đúng quy tắc của release đó.

Một vài hệ quả:

- **Thư viện public** dùng preview có thể làm hạn chế tập JDK mà downstream clients được phép dùng.
- Phát hành một JAR chứa class file preview của Java 24 không biến nó thành JAR có thể chạy tự do trên JVM Java 25; cần kiểm tra quy tắc version, đặc biệt minor marker `65535`.
- Nếu chỉ dùng preview cho thử nghiệm, nên giữ artifact thử nghiệm riêng, không trộn với bản stable được công bố.
- Đánh dấu release/JDK và cách build trong tài liệu của artifact để người khác không phải đoán.
- Các công cụ phân tích bytecode, coverage, instrumentation hoặc shading/packaging phải hiểu class file version đang dùng; plugin cũ có thể thất bại trước cả khi chạy ứng dụng.

Không nên dựa vào việc “máy developer có JDK 24” để kết luận môi trường production/CI có thể đọc bytecode đó. Kiểm tra **JDK đang chạy thực tế** và artifact thật sau đóng gói.

## 10. Lỗi thường gặp và hướng xử lý

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| `... is a preview feature and is disabled by default` | Source dùng preview nhưng compiler chưa bật | Chọn đúng JDK release và thêm `--enable-preview --release N` |
| `invalid source release X with --enable-preview` | JDK compiler không hỗ trợ preview của release X | Dùng `javac` thuộc chính release muốn thử, hoặc bỏ preview nếu dùng ngôn ngữ ổn định |
| `UnsupportedClassVersionError: Preview features are not enabled` | Runtime gặp class file preview nhưng JVM chưa bật | Chạy bằng JVM của release tương ứng và thêm `--enable-preview` |
| `UnsupportedClassVersionError` với major version mới hơn | Runtime quá cũ để đọc class file | Kiểm tra `javac -version`, `java -version`, target `--release` và dependency |
| Cú pháp preview Java N không biên dịch ở Java N+1 | Tính năng đổi cú pháp, được final hoặc bị loại bỏ | Đọc JEP/tài liệu release mới, cập nhật mã và compile lại |
| Chạy từ IDE được nhưng JAR chạy terminal lỗi | Run configuration có JVM flag, terminal thiếu | So sánh args JVM ở từng đường chạy |
| Test pass ở máy nhưng fail CI | Toolchain, plugin hoặc runner chọn JDK khác | Khóa release/toolchain, kiểm tra logs và chạy test với cùng JVM flags |
| Lỗi trong dependency JAR chứa preview | Artifact khác version hoặc compiler/runtime không tương thích | Xác nhận dependency là bản hỗ trợ release mục tiêu, nâng/biên dịch lại thư viện nếu cần |
| `--release 17` không nhận syntax preview Java 24 | Target release thấp hơn preview mong muốn | Quyết định lại yêu cầu runtime; không thể phát hành preview 24 cho runtime 17 bằng flag |
| Cờ bật preview nhưng JVM vẫn báo lỗi khác | Lỗi có thể do classpath, module access, binary mismatch hoặc logic | Đọc stack trace chi tiết, không quy mọi lỗi về preview |

### 10.1. Quy trình kiểm tra nhanh

~~~sh
javac -version
java -version
javac --help
java --help
~~~

Đối với class file cụ thể:

~~~sh
javap -verbose PreviewExample.class
~~~

Đọc `major version` và `minor version`; phân biệt bytecode ổn định với bytecode dùng preview. Với class file không tìm thấy, kiểm tra classpath/module path và vị trí file trước; không cần thêm preview flag nếu vấn đề chỉ là thiếu đường dẫn.

Trong build tool, lấy câu lệnh compiler/test JVM thực tế thay vì chỉ đọc một phần cấu hình. Đừng dùng kết quả `javac -version` từ terminal làm bằng chứng cho toolchain của toàn bộ IDE/CI.

## 11. Quản lý vòng đời preview qua các lần nâng JDK

Một cách sử dụng preview có kỷ luật:

1. **Xác định JEP/release.** Ghi feature ở trạng thái preview của Java nào, link tài liệu phù hợp.
2. **Chỉ dùng nơi có lý do.** Học tập, thử nghiệm, đánh giá cú pháp/API hoặc nguyên mẫu, không mặc nhiên đưa vào mọi thư viện.
3. **Khóa môi trường.** Chọn đúng JDK N bằng toolchain, container hoặc CI image kiểm soát; tránh dựa vào JDK trên PATH.
4. **Bật cả hai phía.** Compile với `--enable-preview --release N`, run/test với JVM N và `--enable-preview` nếu có class/feature preview.
5. **Gắn kiểm thử lỗi/đối chứng.** Kiểm tra build không có flag thất bại như dự đoán với source preview; build đúng chạy theo stdout kỳ vọng.
6. **Kiểm tra artifact.** Xem class file version, packaged JAR và runtime thực tế.
7. **Theo dõi release tiếp theo.** Khi feature được re-preview, finalized hoặc removed, đọc JEP mới trước khi nâng.
8. **Biên dịch lại và kiểm thử.** Không mang nguyên bytecode preview sang JVM mới và chỉ thêm flag để hy vọng chạy được.
9. **Loại bỏ cờ dư.** Khi mã đã chuyển sang phiên bản ổn định và không dùng preview API/VM khác, bỏ `--enable-preview` ở compile và run.
10. **Không phá hợp đồng version.** Nếu sản phẩm cam kết chạy Java 17, không đưa preview Java 24 vào đường chạy chính.

### 11.1. Khi tính năng được final

Sau khi một preview được final, cú pháp có thể giữ tương tự hoặc đã đổi giữa các lần preview. Không đơn giản xóa flag rồi tin rằng tất cả API và hành vi tương thích. Quy trình đúng là:

- Đọc đặc tả/JEP **của release final**.
- Kiểm tra source tương thích với cú pháp và API final.
- Compile **không** bật preview của release đích.
- Chạy unit/integration tests bằng đúng JVM sản phẩm.
- Kiểm tra có phụ thuộc preview khác trong cùng nguồn/dependency không.
- Chốt lại thông tin release và hỗ trợ runtime trong tài liệu dự án.

Với module import declarations, Java 24 là second preview, Java 25 là final. Do đó **ví dụ dùng Java 24 được giữ cố định** trong bài để minh họa rõ ý nghĩa cần enable preview ở cả hai giai đoạn; muốn học cú pháp final hãy dùng tài liệu Java 25 trở lên.

## 12. Bài tập tự luyện có lời giải định hướng

**Bài 1 — Phân biệt hai lỗi.** Dùng JDK 24, biên dịch `PreviewExample.java` không có `--enable-preview`, rồi compile đúng và chạy không có `--enable-preview`. Trường hợp đầu lỗi thuộc **javac**, trường hợp sau lỗi thuộc **JVM**. Vì sao cả hai đều cần cờ độc lập?

**Bài 2 — Nhìn class file.** Dùng `javap -verbose` so sánh `PreviewExample.class` và `StableExample.class` cùng compile với `--enable-preview --release 24`. Giá trị major đều 68; minor của lớp dùng preview là 65535, lớp ổn định mẫu là 0. Vì sao class ổn định chạy được khi không bật preview?

**Bài 3 — Sai source level.** Trên javac 24, thử `--enable-preview --release 17`. Giải thích tại sao javac từ chối ngay cả trước khi bạn xét cú pháp nguồn. Nếu muốn thử preview Java 17, nên chọn JDK nào?

**Bài 4 — Lên release final.** Nghiên cứu module import declarations ở Java 24 và Java 25. Hãy nêu trạng thái mỗi bản. Vì sao không nên tiếp tục mô tả tính năng đó là “preview ở mọi Java mới”?

**Bài 5 — IDE khác terminal.** Dự án chạy từ IDE nhưng `java -cp . PreviewExample` ngoài terminal lỗi. Hãy kiểm tra JDK chạy, launcher flags, classpath/module path và vị trí bytecode, trước khi chỉnh sửa source.

**Bài 6 — Build tool.** Trong Gradle/Maven, compiler đã bật preview nhưng test JVM chưa bật. Hãy xác định nơi cần cấu hình JVM arguments; kiểm tra test runner có đúng JDK release hay không.

**Bài 7 — Chiến lược triển khai.** Hệ thống production chỉ hỗ trợ Java 17, nhóm thử nghiệm muốn dùng preview Java 24. Bạn sẽ tách module/branch/test artifact, toolchain, CI và release pipeline như thế nào để không đưa class file preview Java 24 vào hệ thống chạy Java 17?

## 13. Checklist trước khi dùng preview trong dự án Java

- **Đúng tính năng:** đã xác nhận tính năng là preview, incubator hay final ở release cụ thể.
- **Đúng compiler:** `javac -version` bằng release chứa preview mong muốn.
- **Đúng target:** `--enable-preview --release N` (hoặc `-source N` khi thực sự phù hợp).
- **Đúng runtime:** JVM **N** và `--enable-preview` khi chạy class/feature preview.
- **Đúng bytecode:** xem `major/minor version`, không sửa class file bằng tay để vượt chặn.
- **Đúng dependency:** không vô tình nhận thư viện preview của release khác.
- **Đúng tooling:** IDE/Gradle/Maven/CI/test runner truyền flags cho đúng tiến trình.
- **Đúng vòng đời:** có kế hoạch cập nhật khi preview đổi hoặc final.
- **Đúng phạm vi:** thử nghiệm được cô lập; không phát hành artifact preview nếu sản phẩm yêu cầu runtime ổn định/đời cũ.
- **Đúng kiểm chứng:** test cả trường hợp thiếu flag (lỗi mong đợi) lẫn trường hợp đủ flag (chạy thành công).

**Kết luận:** preview không phải một chế độ “bật là dùng mọi tính năng Java tương lai hoặc quá khứ”. Nó là hợp đồng **gắn chặt với một JDK/release cụ thể**. Với class thực sự dùng preview của Java N, cần biên dịch theo Java N có bật preview và chạy trên runtime Java N được cấu hình tương ứng. Khi nâng release, phải xem lại trạng thái tính năng, biên dịch lại từ nguồn và kiểm thử toàn bộ đường chạy.

## 14. Tài liệu chính thức

- Oracle, *Preview Language and VM Features* — Java SE 24: https://docs.oracle.com/en/java/javase/24/language/preview-language-and-vm-features.html
- Oracle, *Module Import Declarations* — Java SE 24: https://docs.oracle.com/en/java/javase/24/language/module-import-declarations.html
- Oracle, *Java Language Changes by Release* — Java SE 25: https://docs.oracle.com/en/java/javase/25/language/java-language-changes-release.html
- Oracle, *The javac Command* — Java SE 24: https://docs.oracle.com/en/java/javase/24/docs/specs/man/javac.html
- Oracle, *The java Command* — Java SE 24: https://docs.oracle.com/en/java/javase/24/docs/specs/man/java.html
- OpenJDK, *JEP 12: Preview Features*: https://openjdk.org/jeps/12
- OpenJDK, *JEP 494: Module Import Declarations (Second Preview)*: https://openjdk.org/jeps/494
- OpenJDK, *JEP 511: Module Import Declarations*: https://openjdk.org/jeps/511

Khi nội dung trên mạng nói chung chung “Java mới nhất hỗ trợ preview X”, hãy xác định **nó nói về release nào**. Tên tính năng có thể giống nhau qua nhiều JEP nhưng trạng thái và cách dùng cụ thể lại khác theo release.