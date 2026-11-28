# Chọn JDK hiện đại còn được hỗ trợ để thực hành các kiến thức của module

> **Chương:** Phạm vi và nền tảng  
> **Module:** `JAVA_VERSION_JAVA18`  
> **Mục tiêu thực hành:** Chọn một JDK vẫn được cập nhật, cài và xác minh đúng bộ công cụ, sau đó học các thay đổi bền vững được đưa vào Java 18: UTF-8 mặc định, Simple Web Server, Javadoc snippet, Internet-address resolver SPI và cơ chế core reflection dùng method handles.  
> **Mốc đối chiếu vòng đời:** 27/11/2026. Chính sách và bản vá của từng nhà phân phối có thể thay đổi; luôn kiểm tra lại nguồn của nhà phân phối trước khi cài cho dự án thực tế.

## 1. Chọn môi trường cho bài học Java 18 theo mục tiêu hiện tại

**Không cần cài JDK 18 để học các kiến thức còn hữu ích của Java 18.** Những cải tiến được phát hành chính thức trong Java 18 tiếp tục có thể được học và kiểm chứng trên JDK mới hơn. Dùng một bản JDK còn được cung cấp các bản vá bảo mật giúp tránh biến môi trường học tập thành một hệ thống đã hết cập nhật.

Đề xuất mặc định tại thời điểm 27/11/2026:

- **Học mới, không bị ràng buộc bởi dự án:** dùng **JDK 25 LTS**, bản vá mới nhất do nhà phân phối đang hỗ trợ cung cấp.
- **Dự án hoặc lớp học đã chuẩn hóa Java 21:** dùng **JDK 21 LTS**, cập nhật bản vá hiện hành của nhà phân phối. Java 21 đã chứa những thay đổi ổn định từ Java 18.
- **Cần đối chiếu hành vi trên bản feature release mới nhất:** có thể thêm **JDK 27** vào bộ test. Đây là bản feature release có chu kỳ hỗ trợ ngắn; quản lý việc chuyển lên bản tiếp theo.
- **Chỉ còn JDK 17:** vẫn có nhà phân phối hỗ trợ JDK 17, nhưng đây **không phải** JDK thích hợp để chạy trọn bộ bài về các API/công cụ xuất hiện từ Java 18.

Cần phân biệt **phiên bản Java** (17, 18, 21, 25, 27) với **bản phân phối JDK** (Eclipse Temurin, Amazon Corretto, Oracle JDK, v.v.). Mốc LTS và thời gian cập nhật, điều khoản phân phối và mức hỗ trợ phụ thuộc nhà cung cấp; “chọn Java 25” mới là nửa đầu của quyết định.

Sau bài này, người học có thể tự trả lời:

1. Vì sao JDK 25 hoặc 21 đáp ứng tốt hơn JDK 18 cho môi trường thực hành hiện tại?
2. Nhà phân phối nào cam kết cập nhật đến khi nào, trên đúng hệ điều hành/kiến trúc cần dùng?
3. Cách kiểm chứng `java`, `javac`, `javadoc` và `jwebserver` cùng thuộc một JDK?
4. Cách chứng minh một API xuất hiện từ Java 18 bằng `javac --release` và cách quan sát hành vi ở runtime?
5. Khi thấy một khác biệt, cách tách lỗi cài đặt, cấu hình hệ điều hành, hợp đồng API và thay đổi nội bộ JDK?

## 2. Vòng đời Java: bản “mới nhất” và bản “còn được hỗ trợ” là hai tiêu chí

### 2.1. Những lựa chọn phù hợp tại tháng 11/2026

| Dòng JDK | Loại phát hành | Tình trạng và vai trò | Nên dùng cho module? |
|---|---|---|---|
| **18** | Feature release, phát hành 03/2022 | Đã bị các feature release sau thay thế; dòng phát hành cũ không còn được cập nhật thông thường | **Không chọn để thực hành hằng ngày** |
| **17** | LTS, phát hành 09/2021 | Vẫn có nhà phân phối cung cấp bản vá, nhưng **thấp hơn mốc ra đời** của JEP 400/408/413/418/416 | Chỉ dùng khi **so sánh hành vi trước Java 18** |
| **21** | LTS, phát hành 09/2023 | Được các nhà phân phối lớn tiếp tục hỗ trợ | **Phù hợp**, nhất là khi dự án đã dùng 21 |
| **25** | LTS, phát hành 09/2025 | **LTS mới nhất** tính đến 27/11/2026; có vòng đời cập nhật dài | **Ưu tiên cho người học mới** |
| **26** | Feature release, phát hành 03/2026 | Đã bị Java 27 thay thế trong chu kỳ phát hành sáu tháng | Không cần chọn thay 25/27 |
| **27** | Feature release, phát hành 09/2026 | Bản Java mới nhất tại mốc đối chiếu; vẫn nhận cập nhật ngắn hạn | **Tùy chọn để kiểm thử chéo**, có kế hoạch nâng bản |

Theo [Oracle Java SE Support Roadmap](https://www.oracle.com/java/technologies/java-se-support-roadmap.html), Java 21 và 25 thuộc dòng LTS; Java 27 là bản không phải LTS. [Oracle Java Downloads](https://www.oracle.com/java/technologies/downloads/) xác nhận ở thời điểm đối chiếu Java 27 là bản phát hành mới nhất và Java 25 là LTS mới nhất. Lịch phát hành không phải cam kết rằng mọi bản phân phối JDK đều nhận các bản vá trong cùng khoảng thời gian.

**Điểm cần nhớ:** JDK 17 còn được hỗ trợ không đồng nghĩa JDK 17 chứa `InetAddressResolverProvider` hoặc `jwebserver`. “Còn hỗ trợ” và “đủ khả năng chạy bài thực hành” phải được xét **đồng thời**.

### 2.2. Ví dụ về thời gian hỗ trợ *theo nhà phân phối*

Các mốc dưới đây là thông tin từ trang chính thức được kiểm tra tại 27/11/2026. Không dùng chúng làm lời bảo đảm vĩnh viễn cho một hợp đồng hoặc một phiên bản mới trong tương lai.

| Nhà phân phối, dòng JDK | Mốc công bố | Ý nghĩa cần hiểu |
|---|---|---|
| **Eclipse Temurin 25 LTS** | Dự kiến hỗ trợ đến **ít nhất 09/2031** | Dòng build LTS được Adoptium cập nhật; cần dùng bản vá mới nhất và kiểm tra nền tảng được hỗ trợ |
| **Eclipse Temurin 21 LTS** | Dự kiến hỗ trợ đến **ít nhất 12/2029** | Phù hợp với dự án chuẩn hóa 21 |
| **Amazon Corretto 25 LTS** | Kết thúc vòng đời công bố **10/2032** | Nhà phân phối dự kiến phát hành bản vá đến mốc công bố |
| **Amazon Corretto 21 LTS** | Kết thúc vòng đời công bố **10/2030** | Lựa chọn dài hạn cho ứng dụng đang dùng Java 21 |
| **Oracle Java SE 25 LTS** | Premier Support đến **09/2030**, Extended Support đến **09/2033** | Đây là **hạng hỗ trợ sản phẩm Oracle**; quyền nhận hỗ trợ, cập nhật và giấy phép tùy điều kiện áp dụng |
| **Oracle Java SE 21 LTS** | Premier Support đến **09/2028**, Extended Support đến **09/2031** | Cũng phải kiểm tra hạng dịch vụ và điều khoản giấy phép hiện hành |
| **Java 27 non-LTS** | Trong lộ trình Oracle, Premier Support dự kiến đến **03/2027** | Mục đích là bắt kịp feature release; cần tính kế hoạch lên bản kế tiếp |

Nguồn trực tiếp: [Eclipse Temurin Support](https://adoptium.net/support), [Amazon Corretto FAQ / Support Calendar](https://aws.amazon.com/corretto/faqs/) và [Oracle Java SE Support Roadmap](https://www.oracle.com/java/technologies/java-se-support-roadmap.html).

“LTS” không tự bảo đảm mọi kiểu hỗ trợ đều miễn phí, tồn tại vô hạn hoặc có chính sách giống nhau. Ví dụ, **Oracle JDK 21** đã chuyển cơ chế cấp phép cho một số bản cập nhật kể từ **20/10/2026**, theo thông báo trên Oracle support roadmap; điều khoản này không đồng nghĩa với điều khoản phát hành Eclipse Temurin hay Amazon Corretto. Khi cài JDK trong công ty, phải đọc giấy phép và chính sách hỗ trợ **đúng nhà phân phối, đúng bản build, đúng cách dùng**.

### 2.3. “Được hỗ trợ” cần được kiểm tra bằng điều gì?

Một lựa chọn JDK được xem là phù hợp khi cùng thỏa mãn:

- **Còn nhận bản vá:** dòng phát hành chưa hết vòng đời cập nhật theo nhà phân phối, có thông báo bảo mật/bản build mới.
- **Hỗ trợ nền tảng:** có gói phù hợp hệ điều hành và kiến trúc CPU, ví dụ Windows x64, macOS ARM64, Linux x64/aarch64; không giả định mọi nhà phân phối đều có mọi tổ hợp.
- **Cung cấp đủ công cụ:** phải là **JDK**, có `javac`, `javadoc` và công cụ/module cần cho bài, thay vì chỉ một JRE rút gọn.
- **Phù hợp pháp lý/vận hành:** điều khoản giấy phép, cách nhận cập nhật, checksum/chữ ký và chính sách công ty.
- **Phù hợp dự án thực tế:** build tool, framework, thư viện native, IDE, CI và production có thể sử dụng phiên bản đã chọn.

Nếu máy dùng bản cài lâu năm nhưng dòng JDK vẫn còn được hỗ trợ, **bản build cũ chưa tự động an toàn**. Cần cập nhật về bản vá được nhà phân phối khuyến nghị. Tương tự, không lấy ngày phát hành “Java 25” làm bằng chứng máy đã có các bản vá mới trong năm 2026.

## 3. Sơ đồ quyết định chọn JDK cho học viên

~~~text
Bắt đầu
   |
   v
Có yêu cầu JDK do dự án/đơn vị quy định?
   |
   +-- Có --> JDK đó >= 18 và nhà phân phối vẫn cập nhật?
   |                    |
   |           +--------+--------+
   |           |                 |
   |          Có                Không
   |           |                 |
   |      Dùng đúng bản      Thống nhất phương án
   |      được hỗ trợ        bổ sung JDK 21/25
   |           |
   +-- Không -+
              |
              v
       Chọn JDK 25 LTS
       + bản vá hiện hành
              |
              v
  Có IDE/CI/production cần đối chiếu?
              |
       +------+------+
       |             |
      Có           Không
       |             |
  Bổ sung JDK 21   Bắt đầu thực hành
  hay 27 tùy mục   với JDK 25
  tiêu kiểm thử
~~~

**Khuyến nghị rõ ràng:**

- **Môi trường học cá nhân mới:** Eclipse Temurin 25 LTS là một lựa chọn hợp lý vì có gói JDK phổ biến, tài liệu cài đặt và lịch cập nhật công khai.
- **Học trong hệ thống đang dùng Corretto:** chọn Corretto 25 hoặc 21 tương ứng với runtime/CI của hệ thống; kiểm tra roadmap Corretto.
- **Môi trường thương mại dùng Oracle JDK:** dùng phiên bản và bản vá phù hợp với điều khoản giấy phép/hỗ trợ của tổ chức.
- **Cần phát hiện khác biệt phiên bản sớm:** xây dựng bài kiểm thử trên JDK LTS chính và chạy thêm trên JDK 27 như một job bổ trợ. Không yêu cầu người mới thay mọi công cụ sang feature release ngắn hạn.

Không có nhà phân phối “đúng nhất” cho mọi máy. Chọn **dòng Java**, rồi chọn **build được nhà phân phối hỗ trợ trên nền tảng thực**, sau đó ghi lại phiên bản cụ thể để tái hiện kết quả.

## 4. Cài một bản JDK đầy đủ, có thể kiểm chứng

### 4.1. Lấy từ nguồn chính thức

Các điểm tải và tài liệu cài đặt:

| Nhà phân phối | Tải hoặc cài đặt | Kiểm tra vòng đời |
|---|---|---|
| **Eclipse Temurin** | [Temurin Releases](https://adoptium.net/temurin/releases/) · [Installation Guide](https://adoptium.net/installation) | [Temurin Support](https://adoptium.net/support) |
| **Amazon Corretto** | [Amazon Corretto](https://aws.amazon.com/corretto/) · [Corretto Documentation](https://docs.aws.amazon.com/corretto/) | [Corretto FAQ](https://aws.amazon.com/corretto/faqs/) |
| **Oracle JDK** | [Java Downloads](https://www.oracle.com/java/technologies/downloads/) | [Oracle Support Roadmap](https://www.oracle.com/java/technologies/java-se-support-roadmap.html) |

Khi chọn trên trang tải, kiểm tra đủ **JDK 25 (hoặc 21)**, kiến trúc CPU, hệ điều hành, kiểu gói và bản vá mới nhất. Sử dụng checksum/chữ ký do nhà phân phối công bố khi quy trình bảo mật yêu cầu; tránh tải installer từ trang trung gian không rõ nguồn gốc.

Đối với **Windows có WinGet**, Adoptium hiện công bố ví dụ cài Temurin 25:

~~~powershell
winget install EclipseAdoptium.Temurin.25.JDK
~~~

Chạy trên PowerShell/Terminal có WinGet và quyền cài đặt phù hợp. Sau khi cài, mở **terminal mới** để nạp lại biến môi trường, rồi kiểm tra theo phần tiếp theo. Nếu không dùng WinGet, tải gói JDK x64/ARM64 phù hợp trên trang Temurin và làm theo hướng dẫn của nhà phân phối.

Đối với macOS và Linux, dùng gói chính thức tương ứng (`.pkg`, `.deb`, `.rpm`, `.tar.gz` ... tùy hệ điều hành) hoặc trình quản lý gói được nhà phân phối hướng dẫn. Tên package và kho cung cấp thay đổi theo phiên bản hệ điều hành, vì vậy nên theo [tài liệu cài đặt hiện hành](https://adoptium.net/installation) thay vì sao chép một câu lệnh chưa được kiểm tra trên máy đó.

### 4.2. Kiểm tra có đúng *JDK* và đúng bản vá

Sau khi cài, mở một terminal mới và chạy:

~~~shell
java -version
javac -version
javadoc --version
jwebserver --version
~~~

Ví dụ minh họa một máy dùng JDK 25 được cập nhật sẽ có số phiên bản thuộc dòng `25.0.x` ở `java`/`javac`; **số patch cụ thể không phải yêu cầu cố định của bài**, vì có bản vá mới theo chu kỳ. Các công cụ phải thuộc **cùng một bộ JDK mà bạn định sử dụng**. Nếu `java` cho thấy 25 nhưng `javac` cho thấy 17, hoặc không tìm thấy `javadoc`, môi trường đang bị lệch PATH/JAVA_HOME hoặc dùng runtime thiếu công cụ.

Kiểm tra module phục vụ Simple Web Server:

~~~shell
java --describe-module jdk.httpserver
~~~

Nếu JDK cung cấp module này, lệnh mô tả module và các package liên quan. Nếu báo `Module jdk.httpserver not found`, cần kiểm tra bản phân phối/bộ runtime đang dùng. Không mặc định kết luận JDK “bị lỗi” nếu bạn đang chạy một **custom runtime image** đã chủ động loại module.

### 4.3. Trên Windows: xác định lệnh nào thực sự được gọi

PowerShell:

~~~powershell
Get-Command java, javac, javadoc, jwebserver
where.exe java
where.exe javac
$env:JAVA_HOME
~~~

`where.exe` và `Get-Command` giúp phát hiện nhiều JDK có trên `PATH`. Biến `JAVA_HOME` thường trỏ tới **thư mục gốc JDK**, không phải thư mục `bin`. Tùy công cụ, `JAVA_HOME` và `PATH` có thể được đọc theo cách khác nhau; cần kiểm tra cả hai.

Một tình huống thường gặp:

~~~text
JAVA_HOME -> JDK 25
PATH      -> .../jdk-17/bin ; .../jdk-25/bin
java -version  -> 17 ...
javac -version -> 17 ...
~~~

Cách xử lý là sửa thứ tự `PATH` hoặc cấu hình terminal/IDE để gọi chính xác JDK cần dùng; không dựa vào việc máy “đã cài Java 25” để kết luận các lệnh đang dùng đúng JDK 25.

**Không sửa biến môi trường hệ thống một cách mù quáng.** Với môi trường nhiều dự án, có thể cần cấu hình JDK riêng cho từng terminal, IDE, toolchain và pipeline CI.

### 4.4. IDE, build tool và CI phải đồng bộ

Tối thiểu kiểm tra ba nơi:

1. **IDE:** Project SDK/JDK và language level. Một số IDE có runtime riêng để chạy IDE, khác JDK dùng biên dịch dự án.
2. **Build tool:** Maven/Gradle có thể dùng JDK khác terminal; kiểm tra cấu hình toolchain và lệnh báo version của chính công cụ.
3. **CI/CD và production:** Pipeline phải ghi rõ phân phối và major JDK, lý tưởng có cơ chế lấy bản vá mới của dòng đang hỗ trợ; production có thể chạy trên runtime image riêng.

Một dự án có thể **biên dịch bằng JDK 25 với `--release 18`** nhưng vẫn phải test trên runtime mà nó thực sự hỗ trợ. `--release` giới hạn source/bytecode/API của release đích, **không biến JDK 25 thành JVM Java 18**.

## 5. Kiểm thử tối thiểu: JDK đã chứa API Java 18 chưa?

Thay vì dựa vào một màn hình “About Java”, hãy tạo ví dụ Java nhỏ sử dụng những thành phần đặc trưng. Bài kiểm thử dưới đây chỉ cần một tệp nguồn, không cần cấu hình DNS hoặc framework.

Tạo `Java18EnvironmentCheck.java`:

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.reflect.Method;
import java.net.spi.InetAddressResolverProvider;
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;

public final class Java18EnvironmentCheck {
    public static String greet(String name) {
        return "Xin chào, " + name;
    }

    public static void main(String[] args) throws Throwable {
        System.out.println("Java runtime: "
                + Runtime.version());
        System.out.println("Default charset: "
                + Charset.defaultCharset());
        System.out.println("UTF-8 available: "
                + StandardCharsets.UTF_8.name());

        // Lớp SPI xuất hiện trong Java 18 (JEP 418).
        // Chỉ tham chiếu kiểu, không đăng ký provider hoặc đổi DNS.
        System.out.println("Resolver SPI: "
                + InetAddressResolverProvider.class.getName());

        // Reflection API tồn tại từ trước Java 18.
        Method reflected = Java18EnvironmentCheck.class.getMethod(
                "greet", String.class);
        String fromReflection =
                (String) reflected.invoke(null, "Java");

        // MethodHandle API tồn tại từ Java 7;
        // JEP 416 thay cách JDK thực thi core reflection bên trong.
        MethodHandle handle = MethodHandles.lookup().findStatic(
                Java18EnvironmentCheck.class,
                "greet",
                MethodType.methodType(String.class, String.class));
        String fromHandle = (String) handle.invokeExact("Java");

        if (!fromReflection.equals(fromHandle)) {
            throw new AssertionError("Kết quả gọi không khớp");
        }
        System.out.println("Invocation: " + fromHandle);
    }
}
~~~

Chạy bằng JDK 21 hoặc 25 đã cài:

~~~shell
javac -encoding UTF-8 Java18EnvironmentCheck.java
java Java18EnvironmentCheck
~~~

Kết quả kỳ vọng trong cấu hình mặc định:

~~~text
Java runtime: 25.0.x+...
Default charset: UTF-8
UTF-8 available: UTF-8
Resolver SPI: java.net.spi.InetAddressResolverProvider
Invocation: Xin chào, Java
~~~

Dòng phiên bản có thể khác theo JDK và nhà phân phối. Nếu `Default charset` không là UTF-8, kiểm tra cấu hình JVM, đặc biệt `file.encoding`, thay vì kết luận JDK đang thiếu JEP 400. Console không hiển thị đúng dấu tiếng Việt cũng có thể là khác biệt encoding của terminal; cần phân biệt **byte của dữ liệu** với **cách thiết bị đầu cuối hiển thị**.

**Phép thử này xác minh:**

- JDK đủ hiện đại để **biên dịch và chạy** mã có API `InetAddressResolverProvider` của Java 18.
- `Charset.defaultCharset()` cho thấy giá trị runtime được chọn.
- Reflection và MethodHandle đều thực hiện lời gọi đơn giản.

**Phép thử này không chứng minh:** nhà cung cấp JDK còn hỗ trợ bảo mật đến ngày nào, provider DNS đã được cài, mọi cấu hình charset đều là UTF-8, hay cơ chế tối ưu hóa reflection chạy nhanh hơn. Những điều đó cần nguồn và phép thử riêng.

## 6. Dùng `--release` chứng minh giới hạn API theo phiên bản

Một kiểm tra hữu ích là biên dịch **chính cùng tệp `Java18EnvironmentCheck.java`** với hai mức API khác nhau trên JDK 21/25:

~~~shell
javac --release 17 -encoding UTF-8 Java18EnvironmentCheck.java
javac --release 18 -encoding UTF-8 Java18EnvironmentCheck.java
~~~

Lệnh `--release 17` **dự kiến thất bại** tại `java.net.spi.InetAddressResolverProvider` vì API này được giới thiệu ở Java 18. Lệnh `--release 18` **dự kiến thành công** nếu `javac` hiện hành hỗ trợ release 18. Có thể chạy `javac --help` để xem tập release được compiler đang dùng hỗ trợ.

Từ phép thử trên, được kết luận:

- `MethodHandle` có từ Java 7, nên sự hiện diện của nó **không** chứng minh chương trình cần Java 18.
- `InetAddressResolverProvider` được thêm ở Java 18, nên `--release 17` không cho phép tham chiếu API đó.
- Compile ở `--release 18` chứng minh **khả năng dùng API đã được đặc tả**, không tự động chứng minh JVM 18 còn được cập nhật hoặc test runtime của Java 18 đã chạy.

Đọc [`javac` Tool Specification (JDK 25)](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html) để biết `--release` giới hạn ngôn ngữ, class file đích và API platform. Không kết hợp `--release` với `--source` và `--target` trong cùng một lời gọi.

**Lưu ý cho JDK tương lai:** Một compiler chỉ hỗ trợ số lượng giới hạn các release cũ. Nếu `--release 18` không còn được hỗ trợ trong một JDK tương lai, đó là giới hạn của compiler đang dùng; hãy cập nhật cách kiểm chứng hoặc dùng môi trường test phù hợp. Không cố dùng JDK 18 hết hỗ trợ làm môi trường mặc định.

## 7. Kiểm tra Javadoc snippet và Simple Web Server trên JDK đã chọn

Hai thành phần này giúp xác nhận bạn đã cài **JDK đầy đủ** và có công cụ Java 18 cần cho bài học.

### 7.1. Tạo một trang Javadoc có snippet

Tạo `SnippetDemo.java`:

~~~java
/**
 * Ví dụ Javadoc snippet có từ Java 18 (JEP 413).
 *
 * {@snippet lang="java" :
 *     String result = "  Hello  ".strip();
 *     System.out.println(result); // Hello
 * }
 */
public final class SnippetDemo {
    private SnippetDemo() {}

    public static String normalize(String input) {
        return input.strip();
    }
}
~~~

Tạo tài liệu trên JDK 21 hoặc 25:

~~~shell
javadoc -encoding UTF-8 -d api-docs SnippetDemo.java
~~~

Mở HTML sinh ra và xác nhận snippet được trình bày đúng. `javadoc` **không tự chạy/test đoạn mã trong snippet**, nên khi ví dụ đại diện hành vi API quan trọng, phải có kiểm thử độc lập. Cú pháp `{@snippet}` là một phần của standard doclet, không phải API `MethodHandle` hay thay đổi compile của JVM.

### 7.2. Phục vụ thư mục HTML trên loopback

Tại đúng thư mục chứa `api-docs` vừa tạo:

~~~shell
jwebserver -d api-docs -p 8000 -b 127.0.0.1
~~~

Mở `http://127.0.0.1:8000/` bằng trình duyệt, hoặc từ một terminal khác:

~~~shell
curl -I http://127.0.0.1:8000/
~~~

`GET` và `HEAD` là những phương thức mà công cụ hỗ trợ để phục vụ nội dung tĩnh. Dừng server bằng `Ctrl+C`. Nếu cổng `8000` đã có ứng dụng chiếm dụng, chọn cổng khác, ví dụ `-p 8001`.

Theo [`jwebserver` Tool Specification trên JDK 25](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jwebserver.html), đây là máy chủ HTTP tối giản cho việc phát triển, thử nghiệm và gỡ lỗi, **không hỗ trợ HTTPS/HTTP/2** và không nhằm làm server production. Dùng loopback bảo đảm yêu cầu thử nghiệm không tự mở truy cập từ mạng khác tới thư mục học tập.

### 7.3. Có cần kiểm tra resolver SPI bằng DNS thật không?

Chưa cần trong bài kiểm tra cài đặt. Dòng `InetAddressResolverProvider.class.getName()` đã xác nhận class có mặt. **Hành vi provider tùy biến** là bài chuyên sâu khác: phải đăng ký provider qua `ServiceLoader` (module service declaration hoặc `META-INF/services`), tạo JVM mới để kiểm soát lần chọn resolver và chú ý cache `InetAddress`.

Tự gọi `InetAddress.getByName("example.com")` chỉ kiểm tra đường phân giải tên đang hoạt động trong môi trường hiện tại; **không chứng minh** ứng dụng đã đăng ký hay sử dụng provider tùy biến của JEP 418. Đối với máy không có mạng hoặc proxy bị giới hạn, phép thử DNS ngoài còn dễ cho kết quả sai lệch.

### 7.4. Có cần tự kiểm tra implementation reflection của JEP 416 không?

Không nhất thiết. Ví dụ trong phần 5 kiểm tra **hợp đồng công khai** của `Method.invoke` và `MethodHandle.invokeExact`. Việc JDK 18 tái triển khai core reflection trên nền tảng method handles là thông tin của [JEP 416](https://openjdk.org/jeps/416), không thể suy luận chỉ từ việc hai cách gọi cho cùng chuỗi đầu ra.

`MethodHandle` và `MethodHandles` đã có từ Java 7; Java 18 không tạo API này. Trên JDK mới, tiếp tục chọn reflection hoặc MethodHandle theo hợp đồng và nhu cầu của ứng dụng. Không cài cờ `jdk.reflect.useDirectMethodHandle=false` để “khôi phục cách cũ”: từ JDK 22, implementation core reflection cũ đã bị loại bỏ và cờ chuyển thành **no-op**, theo ghi chú phát hành của JDK 22.

## 8. Làm việc với nhiều JDK mà không nhầm phiên bản

Một máy phát triển có thể cần JDK 21 cho dự án đang vận hành, JDK 25 cho module học này và JDK 27 để kiểm tra tính tương thích sớm. Cách quản lý bền vững là **ghi rõ phiên bản ở nơi thực sự thực thi**.

| Nơi cấu hình | Điều nên ghim hoặc xác nhận | Phép kiểm |
|---|---|---|
| Terminal của học viên | `PATH`, `JAVA_HOME`, vị trí `java`/`javac` | `java -version`, `javac -version` |
| IDE | Project SDK và compiler language level | Build/Run một class có API Java 18 |
| Maven/Gradle | Toolchain/JDK chạy build và release target | Lệnh version của build tool; đối chiếu compiler thực |
| CI | Nhà phân phối, major JDK và cơ chế lấy patch | Log version tại đầu pipeline |
| Production | Runtime thật, vendor, patch, module có sẵn | Metadata image và kết quả smoke test có kiểm soát |

**Ví dụ chính sách dự án:**

~~~text
JDK dùng để phát triển bài Java 18:
  Major: 25 (LTS)
  Distribution: Eclipse Temurin
  Patch: bản mới nhất đã được đơn vị kiểm thử chấp nhận
  OS/architecture: ghi từ môi trường thực
  Build API target: theo yêu cầu bài hoặc dự án
  Runtime test: JDK 25 cùng distribution đã chọn
  Extra validation: JDK 21 khi dự án đòi hỏi; JDK 27 nếu kiểm tra chéo
  Cập nhật: theo thông báo security/PSU của distribution
~~~

Khi chạy CI, **không chỉ dùng** `--release` rồi coi công việc xong: một đoạn mã có thể biên dịch theo target cũ nhưng ứng dụng vẫn phụ thuộc hành vi runtime, charset hoặc thư viện bên thứ ba. Nên chạy integration/smoke test bằng runtime mục tiêu.

Nếu có nhu cầu build artefact chạy trên nhiều JDK, đặc biệt cần **nhận thức rõ API giới thiệu ở Java 18**. Ví dụ artefact sử dụng `InetAddressResolverProvider` không thể yêu cầu chạy trên JDK 17 theo cách nguyên trạng chỉ vì đã đặt một cờ compiler.

## 9. Quy trình đánh giá nhà phân phối trước khi quyết định

Đây là checklist dùng được về lâu dài, kể cả sau khi mốc Java 25/27 không còn là mới nhất.

| Câu hỏi | Lý do | Dấu hiệu đạt |
|---|---|---|
| Dòng JDK tối thiểu để học đủ tính năng? | Các tính năng module bắt đầu từ Java 18 | JDK từ **18 trở lên** |
| Dòng nào còn được cập nhật và phù hợp lâu dài? | Tránh nền tảng hết bản vá | Chọn LTS còn hỗ trợ, ví dụ 21/25 ở mốc hiện tại |
| Nhà phân phối hỗ trợ OS/CPU của máy? | Không phải mọi gói đều có Windows ARM64, macOS ARM64, Linux khác nhau | Có gói tương thích và tài liệu chính thức |
| Điều khoản sử dụng có phù hợp? | License và hỗ trợ là điều kiện của bản phân phối | Đã đọc chính sách đúng phiên bản |
| Có lịch vá và kênh thông báo? | “LTS” không thay việc vận hành update | Có roadmap và bản build được cập nhật |
| Bộ cài có đủ `javac`, `javadoc`, `jwebserver`? | Bài cần công cụ JDK, không chỉ runtime | Lệnh và `jdk.httpserver` xuất hiện |
| IDE/CI dùng cùng major/vendor theo thiết kế? | Tránh “works on my machine” | Log version và cấu hình có thể tái hiện |
| Có thể biên dịch/đọc API JDK 18? | Kiểm tra tính năng yêu cầu | `--release 18` và smoke test phù hợp |
| Có ràng buộc bảo mật/vận hành đặc biệt? | Hệ thống công ty có thể cần quy chuẩn riêng | Được người quản trị/nhóm nền tảng chấp nhận |

Đối với ứng dụng thương mại, yêu cầu compliance hoặc hỗ trợ trả phí, kết luận cuối cùng cần dựa trên cam kết dịch vụ của nhà cung cấp và chính sách của tổ chức. Đối với bài học cá nhân, chỉ cần một JDK 25 LTS được cập nhật và hoạt động trên máy đã là nền tảng tốt.

## 10. Các lỗi thường gặp và cách xử lý theo nguyên nhân

### Lỗi A — `javac` không được nhận diện

**Hiện tượng:** `java -version` hoạt động nhưng `javac -version` báo không tìm thấy.

**Nguyên nhân thường gặp:** Chỉ cài runtime/JRE, `PATH` thiếu thư mục `bin` của JDK, terminal chưa nạp cấu hình mới, hoặc dùng một runtime image rút gọn.

**Cách kiểm:** Kiểm tra bộ cài là JDK đầy đủ, sử dụng `Get-Command`/`where.exe` hoặc cách tương đương của OS để biết đường dẫn thực, mở terminal mới rồi thử lại.

### Lỗi B — `--release 17` không biên dịch được lớp SPI

**Hiện tượng:** `cannot find symbol` hoặc lỗi liên quan `java.net.spi.InetAddressResolverProvider`.

**Kết luận:** Đây là **kết quả kỳ vọng** khi kiểm chứng giới hạn API, vì lớp SPI được giới thiệu từ Java 18. Đổi sang `--release 18` hoặc mức được dự án hỗ trợ nếu bài thực hành yêu cầu API đó.

### Lỗi C — `jwebserver` không tồn tại

**Hiện tượng:** `jwebserver: command not found` hoặc `'jwebserver' is not recognized`.

**Hướng kiểm:** Kiểm tra JDK thực đang gọi, module `jdk.httpserver` có mặt hay không, và công cụ `bin` của JDK có trên `PATH` hay không. Không lấy việc `java -version` báo số lớn hơn 18 làm bảo đảm mọi custom runtime image đều có công cụ.

### Lỗi D — Terminal in sai tiếng Việt dù `Charset.defaultCharset()` là UTF-8

**Nguyên nhân có thể:** Encoding của console, font, terminal hoặc cách hiển thị byte khác mặc định charset của Java. Không kết luận vòng tròn rằng “JEP 400 sai” chỉ vì ký tự trên màn hình không đúng. Kiểm tra round-trip qua `Files.writeString`/`readString` với `StandardCharsets.UTF_8`, sau đó kiểm tra cấu hình terminal riêng.

### Lỗi E — Hai máy cùng Java 25 nhưng khác kết quả hoặc hiệu năng

**Nguyên nhân có thể:** Patch, vendor, OS, CPU, JVM options, locale, classpath/module path, dữ liệu và ứng dụng khác nhau.

**Hướng xử lý:** Ghi đủ version/vendor/configuration, kiểm thử bằng hợp đồng API, phân loại sự khác biệt đã được đặc tả và chi tiết triển khai. Benchmark MethodHandle/reflection chỉ có ý nghĩa khi chạy trên workload đại diện.

### Lỗi F — JDK 27 mới hơn nên chắc chắn “tốt nhất” để học

Java 27 là bản feature release mới nhất tại mốc đối chiếu, nhưng vòng đời cập nhật ngắn hơn LTS. Nếu mục tiêu là học và thực hành ổn định nhiều tháng/năm, JDK 25 LTS thường là lựa chọn phù hợp hơn. Dùng JDK 27 để **kiểm tra chéo**, có lịch nâng cấp theo feature release.

### Lỗi G — Dùng JDK 18 để giữ nguyên từng ví dụ lịch sử

Các API được phát hành chính thức trong Java 18 phần lớn vẫn còn trên bản mới. Chạy trên bản cũ đã hết cập nhật tạo thêm rủi ro và không đại diện cho cách ứng dụng hiện đại vận hành. Nếu một hành vi chỉ tồn tại trong bản cũ và đã bị loại bỏ, **đó không phải kiến thức nên đưa vào thực hành hiện tại**.

## 11. Bài thực hành có tiêu chí hoàn thành

### Thực hành 1 — Chọn bản JDK có lý do

Tại ngày làm bài, tra cứu support roadmap của ít nhất một nhà phân phối mà bạn có thể sử dụng. Ghi rõ major, patch build, hệ điều hành, kiến trúc, license và mốc cập nhật dự kiến. So sánh JDK 21 LTS và 25 LTS; giải thích lựa chọn cuối cùng.

**Đạt khi:** Phân biệt được chu kỳ hỗ trợ của nhà phân phối với “major Java đã phát hành”, và không chọn JDK 18 hết cập nhật làm môi trường mặc định.

### Thực hành 2 — Audit công cụ được gọi

Chạy `java -version`, `javac -version`, `javadoc --version`, `jwebserver --version` và `java --describe-module jdk.httpserver`. Trên Windows, thêm `where.exe java` và `where.exe javac`.

**Đạt khi:** Có thể chỉ ra chính xác bộ JDK cung cấp các lệnh cần thiết và sửa được hiện tượng PATH/JAVA_HOME trỏ sai phiên bản.

### Thực hành 3 — Phân biệt API availability với runtime

Biên dịch `Java18EnvironmentCheck.java` với `--release 17` và `--release 18`, ghi thông báo tương ứng. Sau đó chạy bản biên dịch thành công trên JDK đã cài.

**Đạt khi:** Giải thích được vì sao lỗi `InetAddressResolverProvider` ở `--release 17` là kỳ vọng; không dùng kết quả compile để suy luận về hiệu năng reflection.

### Thực hành 4 — Tạo và phục vụ tài liệu

Chạy `javadoc` cho `SnippetDemo.java`, dùng `jwebserver` phục vụ thư mục HTML và mở trình duyệt trên loopback.

**Đạt khi:** Snippet xuất hiện đúng trong Javadoc; trình bày rõ `jwebserver` là công cụ dành cho tệp tĩnh và `{@snippet}` không tự chạy test.

### Thực hành 5 — So sánh hai JDK được hỗ trợ

Nếu máy hoặc CI có JDK 21 và 25, chạy cùng một smoke test trên cả hai. Ghi đầy đủ version, vendor, OS, các JVM option quan trọng và kết quả; so sánh dựa trên API specification.

**Đạt khi:** Tách được phần được hợp đồng bảo đảm (ví dụ API hiện diện, kiểu ngoại lệ của `Method.invoke`) với quan sát phụ thuộc môi trường (độ trễ, thứ tự provider, charset console).

## 12. Mẫu “biên bản môi trường” để lưu cùng bài tập

Có thể điền vào báo cáo học tập hoặc issue nội bộ, không cần tạo thêm file cấu hình đặc biệt cho một bài ngắn:

~~~text
Ngày kiểm tra:
Hệ điều hành / kiến trúc CPU:
JDK major / full version:
Distribution / JVM vendor:
Nguồn tải và cách kiểm tra tính xác thực:
Support roadmap / thời điểm hết cập nhật:
Điều khoản sử dụng liên quan:
JAVA_HOME / vị trí java và javac:
javac --release mục tiêu:
Đã xác nhận jdk.httpserver:
Charset.defaultCharset():
Javadoc snippet được tạo:
Simple Web Server GET/HEAD:
Resolver SPI có mặt:
Reflection và MethodHandle chạy:
Những phần chưa được kiểm chứng:
~~~

Khi thay đổi JDK ở các lần học sau, so sánh hai biên bản để biết sự khác biệt đến từ bản vá, nhà phân phối, cấu hình, hay chính chương trình. Mẫu này hữu ích hơn một ảnh chụp `java -version` đơn lẻ.

## 13. Nguồn chính thức để đối chiếu lại theo thời gian

**Vòng đời và tải JDK**

- [Oracle Java SE Support Roadmap](https://www.oracle.com/java/technologies/java-se-support-roadmap.html) — LTS/non-LTS và mốc hỗ trợ của các sản phẩm Oracle; lưu ý riêng điều khoản cập nhật Oracle JDK.
- [Oracle Java Downloads](https://www.oracle.com/java/technologies/downloads/) — bản Java mới nhất và LTS mới nhất được Oracle công bố.
- [Eclipse Temurin Support](https://adoptium.net/support) — bảng vòng đời của Temurin; tại 27/11/2026 gồm Temurin 21 và 25.
- [Eclipse Temurin Installation Guide](https://adoptium.net/installation) — gói cho Windows, macOS, Linux; công cụ quản lý package và CI.
- [Amazon Corretto FAQs](https://aws.amazon.com/corretto/faqs/) — lịch cập nhật và kết thúc vòng đời theo dòng Corretto.

**API và công cụ liên quan trực tiếp đến bài Java 18**

- [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400), [`Charset` API — Java 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/charset/Charset.html).
- [JEP 408 — Simple Web Server](https://openjdk.org/jeps/408), [`jwebserver` Tool Specification — JDK 25](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jwebserver.html).
- [JEP 413 — Code Snippets in Java API Documentation](https://openjdk.org/jeps/413), [Javadoc Documentation Comment Specification — JDK 25](https://docs.oracle.com/en/java/javase/25/docs/specs/javadoc/doc-comment-spec.html).
- [JEP 418 — Internet-Address Resolution SPI](https://openjdk.org/jeps/418), [`InetAddressResolverProvider` API — Java 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/spi/InetAddressResolverProvider.html).
- [JEP 416 — Reimplement Core Reflection with Method Handles](https://openjdk.org/jeps/416), [`Method` API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/Method.html), [`MethodHandle` API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandle.html).
- [`javac` Tool Specification — JDK 25](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html) — ý nghĩa và giới hạn `--release`.
- [JDK 22 Release Notes](https://www.oracle.com/java/technologies/javase/22-relnote-issues.html) — loại bỏ implementation core reflection cũ của JDK.

**Kết quả cần đạt:** Có một JDK 25 LTS (hoặc JDK 21 LTS khi dự án yêu cầu), được nhà phân phối tiếp tục cập nhật, với `java`/`javac`/`javadoc`/`jwebserver` đúng phiên bản và các phép kiểm Java 18 chạy được. Từ đó người học có thể nghiên cứu **hành vi vẫn được bảo đảm trên JDK hiện đại**, đồng thời nhận biết ranh giới giữa API, cấu hình runtime và chi tiết triển khai.
