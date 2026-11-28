# Chọn JDK còn được hỗ trợ để học các tính năng chính thức của Java 16

> **Chương:** Định hướng Java 16  
> **Phạm vi:** Chọn JDK và bản phân phối còn được cập nhật bảo mật, sau đó dùng môi trường hiện đại để học và thực hành các tính năng đã chính thức ở Java 16. Các mốc hỗ trợ trong bài được đối chiếu ngày **27/11/2026**; lịch hỗ trợ có thể thay đổi theo nhà cung cấp.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao Java 16 không còn là lựa chọn phù hợp cho môi trường phát triển hoặc triển khai thường xuyên.
2. Chọn một JDK LTS đang được hỗ trợ và phân biệt chính sách hỗ trợ của từng nhà cung cấp.
3. Cài đặt, xác minh và cấu hình JDK để IDE cùng công cụ build sử dụng đúng phiên bản.
4. Biên dịch ví dụ Java 16 bằng JDK mới hơn với tùy chọn `--release 16` mà không cần cài JDK 16.
5. Phân biệt khả năng kiểm tra tương thích API với việc kiểm chứng runtime thực tế.

## 1. Không cần dùng JDK 16 để học tính năng chính thức của Java 16

Java 16 được phát hành tháng 3/2021 và là **feature release không thuộc nhóm LTS**. Các bản cập nhật của dòng Java 16 đã kết thúc từ năm 2021 trong lịch phát hành OpenJDK và các lịch hỗ trợ được đối chiếu dưới đây. JDK 16 vì vậy không còn phù hợp làm JDK mặc định cho máy học tập, CI hoặc hệ thống mới cần nhận bản vá bảo mật.

Điều cần học là **những tính năng đã ổn định ở Java 16**, không phải giữ nguyên JDK 16:

- `record` (JEP 395) đã trở thành tính năng ngôn ngữ chính thức ở Java 16.
- Pattern matching cho `instanceof` (JEP 394) đã chính thức ở Java 16.
- `Stream.toList()` và `Stream.mapMulti()` có từ Java 16.
- `jpackage` trở thành công cụ đóng gói chính thức ở Java 16.
- Một số thay đổi JVM và nền tảng ở Java 16 vẫn là kiến thức hữu ích để hiểu lịch sử, tương thích và vận hành.

Các tính năng chính thức này tiếp tục có mặt trên những JDK mới hơn. Có thể dùng một JDK LTS hiện được hỗ trợ để biên dịch ví dụ theo mức Java 16, nhờ tùy chọn `javac --release 16`. Cách này cho phép thực hành cú pháp và API Java 16 mà không phải cài một runtime đã hết vòng đời cập nhật.

## 2. Chọn phiên bản JDK nào ở thời điểm hiện tại?

**Khuyến nghị học tập:** Dùng **JDK 25 LTS làm JDK chính** cho môi trường học và phát triển mới, sau đó đặt `--release 16` khi cần kiểm tra mã nguồn/API thuộc Java 16. Java 25 là bản LTS mới nhất tính đến ngày 27/11/2026. JDK 27 là feature release mới nhất, nhưng không phải LTS và có chu kỳ hỗ trợ ngắn hơn.

| Phiên bản | Trạng thái tại 27/11/2026 | Khi nào chọn? |
| --- | --- | --- |
| **JDK 25** | **LTS mới nhất** | Lựa chọn mặc định cho học tập, phát triển và dự án mới cần chu kỳ hỗ trợ dài |
| JDK 21 | LTS trước đó | Chọn khi framework, nền tảng triển khai hoặc tổ chức chưa chuyển lên 25 |
| JDK 17 | LTS trước đó | Chỉ dùng khi dự án/nhà cung cấp vẫn yêu cầu mức nền tảng 17 |
| JDK 27 | Feature release mới nhất, không phải LTS | Dùng để thử nghiệm tính năng mới hoặc theo kịp feature release khi có kế hoạch nâng cấp thường xuyên |
| JDK 16 | Feature release cũ, đã hết vòng đời cập nhật | Không chọn làm JDK mặc định hoặc runtime triển khai mới |

**LTS không phải một loại ngôn ngữ Java khác.** Đây là cách nhà cung cấp xác định một số bản phát hành được duy trì lâu hơn. Thời hạn, bản vá, điều kiện thương mại và cam kết hỗ trợ có thể khác nhau giữa Oracle JDK, Eclipse Temurin, Amazon Corretto, Azul Zulu, Microsoft Build of OpenJDK, Red Hat build of OpenJDK và các nhà cung cấp khác.

### Mốc hỗ trợ tham khảo từ nhà cung cấp

| Dòng JDK | Lịch hỗ trợ được công bố | Ý nghĩa khi lựa chọn |
| --- | --- | --- |
| Oracle JDK 25 LTS | Premier Support đến 09/2030; Extended Support đến 09/2033 theo roadmap hiện tại | Có thời hạn hỗ trợ dài cho khách hàng thuộc phạm vi hỗ trợ Oracle |
| Oracle JDK 27 | Non-LTS; mốc hỗ trợ Premier hiện tại đến 03/2027 | Không nên chọn làm baseline dài hạn nếu không có kế hoạch nâng phiên bản thường xuyên |
| Eclipse Temurin 25 LTS | Adoptium công bố duy trì ít nhất đến 09/2031 | Lựa chọn OpenJDK distribution phổ biến cho học tập và phát triển |
| Eclipse Temurin 21 LTS | Adoptium công bố duy trì ít nhất đến 12/2029 | Lựa chọn thay thế khi dự án cần mức nền tảng 21 |
| Eclipse Temurin 16 | Đã EOSL từ 09/2021 | Không còn là lựa chọn nhận cập nhật Temurin |

Đây là các mốc của **những chương trình cụ thể**, không phải cam kết chung cho mọi bản phân phối JDK. Oracle Premier/Extended Support là điều kiện dịch vụ của Oracle; mốc Adoptium là lịch duy trì bản dựng Temurin. Nếu tổ chức có hợp đồng hỗ trợ với nhà cung cấp khác, hãy dùng chính sách và SLA của nhà cung cấp đó.

**Quy tắc thực tế:** chọn JDK LTS còn nhận cập nhật từ một nhà cung cấp mà nhóm có thể tải, cập nhật và nhận hỗ trợ; luôn dùng bản cập nhật bảo mật mới nhất trong dòng JDK đã chọn. Không cố định một số bản vá cũ trong hướng dẫn cài đặt.

## 3. Chọn bản phân phối JDK phù hợp

JDK là bộ phát triển; **OpenJDK** là dự án mã nguồn mở làm nền tảng cho nhiều bản phân phối. Một số bản phân phối có thể dùng chung mã nguồn OpenJDK nhưng khác quy trình build, kiểm thử, lịch cập nhật, hỗ trợ, chứng nhận, gói cài và điều khoản sử dụng.

| Bản phân phối | Khi nào nên xem xét? | Điều cần kiểm tra |
| --- | --- | --- |
| **Eclipse Temurin (Adoptium)** | Học tập, phát triển và môi trường cần bản dựng OpenJDK phổ biến | Ma trận hệ điều hành/kiến trúc và lịch duy trì LTS của Adoptium |
| **Oracle JDK** | Tổ chức đang dùng dịch vụ, hỗ trợ hoặc quy trình quản trị Oracle | Điều khoản cấp phép, bản cập nhật và mốc hỗ trợ áp dụng cho tổ chức |
| **Amazon Corretto** | Hệ thống chạy trên AWS hoặc nhóm muốn dùng bản phân phối do Amazon duy trì | Chính sách hỗ trợ, nền tảng và lịch cập nhật Corretto |
| **Azul Zulu** | Nhóm cần lựa chọn nền tảng, hỗ trợ thương mại hoặc bản dựng cụ thể | Phiên bản, chứng nhận, SLA và điều khoản của gói Zulu |
| **Microsoft Build of OpenJDK** | Nhóm phát triển trên nền tảng Microsoft hoặc cần bản dựng được Microsoft duy trì | Phiên bản LTS đang cung cấp và phạm vi hỗ trợ |
| **Red Hat build of OpenJDK** | Hệ thống doanh nghiệp sử dụng nền tảng Red Hat | Vòng đời sản phẩm, hỗ trợ hệ điều hành và chính sách cập nhật |

Đối với người học độc lập, **Eclipse Temurin 25 LTS** là một lựa chọn dễ bắt đầu. Nếu doanh nghiệp đã chuẩn hóa một nhà cung cấp JDK, hãy dùng đúng bản phân phối doanh nghiệp hỗ trợ để tránh khác biệt giữa máy cá nhân, CI và production.

### Tiêu chí chọn trước khi tải

1. **Phiên bản:** ưu tiên JDK 25 LTS; chỉ chọn JDK 21 nếu có yêu cầu tương thích cụ thể.
2. **Hệ điều hành và kiến trúc:** Windows/macOS/Linux; x64 hoặc ARM64 đúng với máy và môi trường triển khai.
3. **Cập nhật bảo mật:** xác định nơi thông báo bản vá và cách cập nhật định kỳ.
4. **Hỗ trợ:** phân biệt hỗ trợ cộng đồng với SLA thương mại, thời gian phản hồi và phạm vi nền tảng.
5. **Điều khoản:** kiểm tra quyền sử dụng, phân phối lại và điều kiện triển khai theo nhà cung cấp.
6. **Tính toàn vẹn:** tải từ website chính thức; kiểm tra checksum/chữ ký nếu nhà cung cấp công bố.

Không cần cài nhiều bản phân phối cùng phiên bản chỉ để học `record` hoặc Stream API. Một JDK LTS phù hợp với hệ điều hành là đủ.

## 4. Cài đặt và xác minh JDK 25

Ví dụ bên dưới dùng Eclipse Temurin 25. Nếu chọn nhà cung cấp khác, thay đường dẫn cài đặt tương ứng và đọc hướng dẫn của nhà cung cấp.

### Bước 1 — Tải JDK

Mở [Eclipse Temurin Releases](https://adoptium.net/temurin/releases/) hoặc trang tải chính thức của nhà cung cấp. Chọn:

- Version: **25 - LTS**.
- Package: **JDK**, không chỉ JRE/runtime.
- Operating System: hệ điều hành đang dùng.
- Architecture: x64 hoặc aarch64/ARM64 phù hợp.
- Installer/package: định dạng cài đặt phù hợp hệ điều hành.

Sau khi cài, ghi lại thư mục JDK. Trên Windows, đường dẫn có thể gần giống `C:\Program Files\Eclipse Adoptium\jdk-25...`; tên thư mục thực tế tùy phiên bản cập nhật. Trên Linux/macOS, đường dẫn phụ thuộc trình quản lý gói hoặc vị trí cài đặt.

### Bước 2 — Đặt `JAVA_HOME` và `PATH`

```powershell
# Thay đường dẫn bằng thư mục JDK 25 thực tế trên máy.
$env:JAVA_HOME = "C:\Program Files\Eclipse Adoptium\jdk-25"
$env:Path = "$env:JAVA_HOME\bin;$env:Path"

java --version
javac --version
where.exe java
where.exe javac
```

Trong PowerShell, các lệnh trên chỉ thay đổi môi trường của cửa sổ hiện tại. Để cấu hình lâu dài, dùng phần Environment Variables của Windows hoặc hướng dẫn cài đặt của nhà cung cấp; sau đó mở terminal mới để kiểm tra.

Trên Linux/macOS, ví dụ khi đã biết chính xác thư mục cài đặt:

```bash
export JAVA_HOME="/path/to/jdk-25"
export PATH="$JAVA_HOME/bin:$PATH"

java --version
javac --version
which -a java javac
```

`JAVA_HOME` nên trỏ tới **thư mục gốc JDK**, còn `PATH` chứa thư mục `bin`. Đừng đặt `JAVA_HOME` trỏ trực tiếp vào `bin`.

### Bước 3 — Xác minh compiler và runtime cùng trỏ đến JDK mong muốn

Chạy:

```bash
java --version
javac --version
jpackage --version
```

Nếu dùng Maven hoặc Gradle, kiểm tra cả JDK mà công cụ build sử dụng:

```bash
mvn -version
gradle --version
```

Các lệnh trên có thể cho thấy một JDK khác với terminal hoặc IDE nếu cấu hình `JAVA_HOME`, `PATH`, Gradle daemon, Maven toolchain hay Project SDK chưa đồng nhất. Sửa cấu hình để compiler và runtime được gọi đúng chủ đích; không chỉ nhìn số phiên bản trong IDE.

## 5. Biên dịch mã Java 16 bằng JDK 25 với `--release 16`

Đây là bước quan trọng nhất để thực hành tính năng Java 16 trên JDK còn được hỗ trợ.

`--release 16` yêu cầu `javac` kiểm tra mã theo:

- Quy tắc ngôn ngữ Java 16.
- API Java SE được cung cấp trong Java 16.
- Định dạng class file tương ứng với Java 16.

Do đó, mã dùng `record`, pattern matching cho `instanceof`, `Stream.toList()` và `Stream.mapMulti()` có thể được kiểm tra bằng JDK 25 với tùy chọn này. Các tính năng đó đã chính thức ở Java 16 nên **không cần** `--enable-preview`.

### Ví dụ thực hành

Tạo file `Java16FeaturesDemo.java`:

```java
import java.util.List;
import java.util.stream.Stream;

public class Java16FeaturesDemo {
    record OrderLine(String sku, int quantity) {}

    static List<Integer> positiveQuantities(List<OrderLine> lines) {
        return lines.stream()
                .<Integer>mapMulti((line, downstream) -> {
                    if (line.quantity() > 0) {
                        downstream.accept(line.quantity());
                    }
                })
                .toList();
    }

    static String describe(Object value) {
        if (value instanceof OrderLine line) {
            return line.sku() + " x " + line.quantity();
        }
        return "Unknown value";
    }

    public static void main(String[] args) {
        var lines = List.of(
                new OrderLine("BOOK", 2),
                new OrderLine("PEN", 0),
                new OrderLine("BAG", 3)
        );

        System.out.println(positiveQuantities(lines)); // [2, 3]
        System.out.println(describe(lines.get(0)));    // BOOK x 2
    }
}
```

Biên dịch bằng compiler JDK 25:

```bash
javac --release 16 -d out Java16FeaturesDemo.java
```

Chạy trên runtime JDK 25:

```bash
java -cp out Java16FeaturesDemo
```

Kết quả mong đợi:

```text
[2, 3]
BOOK x 2
```

Kiểm tra bytecode:

```bash
javap -verbose -classpath out Java16FeaturesDemo
```

Tìm dòng `major version: 60`. Đây là phiên bản class file của Java 16. Runtime JDK 25 có thể chạy class file cũ hơn, miễn là các API và phụ thuộc cần thiết tồn tại, cũng như ứng dụng không phụ thuộc hành vi riêng của runtime cũ.

### Chứng minh API mới không lọt vào baseline cũ

Thử biên dịch lại:

```bash
javac --release 11 -d out11 Java16FeaturesDemo.java
```

Lần biên dịch này phải thất bại vì ví dụ dùng cú pháp record/pattern matching và API Stream được thêm sau Java 11. Đây là minh họa rằng `--release` khóa cả ngôn ngữ lẫn API nền tảng. Khi cần tìm nguyên nhân cụ thể, đọc thông báo lỗi đầu tiên và đối chiếu đúng cú pháp/API liên quan.

**Giới hạn:** `--release 16` xác minh tương thích ở mức compiler với Java SE 16; nó không mô phỏng toàn bộ JVM Java 16, GC, hệ điều hành, native library, reflection hoặc hành vi của từng nhà cung cấp. Không dùng nó để tuyên bố ứng dụng đã được kiểm thử trên runtime Java 16.

## 6. Đặt cấu hình đúng trong IDE và hệ thống build

Máy có thể dùng JDK 25 làm compiler, nhưng đặt baseline Java 16 cho bài tập hoặc một dự án cần tương thích. Cấu hình cần thống nhất giữa IDE, Maven/Gradle, CI và terminal.

### Maven

Với phiên bản `maven-compiler-plugin` hỗ trợ thuộc tính `maven.compiler.release`, cấu hình:

```xml
<properties>
    <maven.compiler.release>16</maven.compiler.release>
</properties>
```

Chọn JDK 25 cho Maven toolchain hoặc môi trường chạy Maven. Thuộc tính `release` điều khiển mức Java mục tiêu; toolchain quyết định JDK compiler thực tế được dùng. Kiểm tra phiên bản plugin và tài liệu build hiện hành nếu dự án có cấu hình compiler riêng.

### Gradle (Kotlin DSL)

Có thể chọn JDK 25 làm toolchain và Java 16 làm release target:

```kotlin
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(25)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release = 16
}
```

Toolchain chọn JDK dùng để biên dịch; `options.release` đặt mức ngôn ngữ/API và bytecode đích. Dùng phiên bản Gradle hỗ trợ JDK 25 và kiểm tra cú pháp DSL với phiên bản plugin Gradle của dự án.

### IDE

Trong IntelliJ IDEA, Eclipse hoặc VS Code với Java extensions:

1. Chọn **Project SDK/JDK 25**.
2. Đặt mức ngôn ngữ hoặc compiler release theo mục tiêu dự án (ví dụ Java 16 cho bài tập này).
3. Kiểm tra cấu hình Maven/Gradle import và toolchain để IDE không tự dùng một JDK khác.
4. Đồng bộ project rồi chạy ví dụ bằng đúng runtime đã chọn.

Nếu IDE báo không hỗ trợ cú pháp trong khi terminal biên dịch thành công, kiểm tra Project SDK và language level. Nếu IDE chạy được nhưng CI thất bại, kiểm tra JDK và tùy chọn `--release` trong pipeline.

## 7. Khi nào dùng JDK 25, JDK 21 hoặc JDK 27?

| Tình huống | Lựa chọn hợp lý | Cách cấu hình |
| --- | --- | --- |
| Học tính năng chính thức Java 16 trên máy mới | JDK 25 LTS | `javac --release 16` |
| Dự án doanh nghiệp đã chuẩn hóa Java 21 | JDK 21 LTS | `--release 21` cho ứng dụng mới; `--release 16` nếu cần kiểm tra baseline cũ |
| Muốn thử tính năng mới nhất của nền tảng | JDK 27 feature release | Dùng branch/lab riêng, theo dõi cập nhật và preview status |
| Ứng dụng production cần vòng đời hỗ trợ dài | JDK LTS còn được vendor hỗ trợ | Theo policy của vendor, cập nhật patch và kiểm thử định kỳ |
| Dự án bắt buộc chạy đúng runtime Java 16 | Lập kế hoạch nâng cấp runtime | Không coi `--release 16` là thay thế cho nâng runtime đã hết hỗ trợ |

JDK 27 có ích nếu bạn cần thử nghiệm những cải tiến mới nhất của Java, nhưng không có lợi thế cần thiết cho bài học Java 16. Một feature release sẽ được thay thế nhanh; nếu không có kế hoạch nâng cấp sau mỗi chu kỳ, hãy chọn LTS.

Nếu một framework hoặc máy chủ ứng dụng chưa hỗ trợ JDK 25, dùng JDK 21 LTS theo ma trận hỗ trợ chính thức của framework. Không ép nâng phiên bản chỉ để làm theo ví dụ. Sau đó lập kế hoạch nâng JDK khi hệ sinh thái phụ thuộc đã sẵn sàng.

## 8. Tổ chức nhiều JDK mà không nhầm phiên bản

Có thể cài nhiều JDK LTS song song để làm việc với các dự án khác nhau. Mỗi dự án cần khai báo JDK toolchain và mức `--release` riêng; tránh thay đổi `JAVA_HOME` toàn cục liên tục mà không ghi lại cấu hình.

Một quy ước dễ quản lý:

| Thành phần | Cấu hình gợi ý |
| --- | --- |
| JDK mặc định cho học tập/dự án mới | JDK 25 LTS |
| JDK tương thích dự án cũ hơn | JDK 21 LTS khi cần |
| Baseline của bài thực hành Java 16 | `--release 16` |
| Runtime dùng để chạy ví dụ | JDK 25 |
| CI | Cài JDK theo toolchain, kiểm tra `java --version` và `javac --version` trước build |

Không tải các bản JDK từ kho lưu trữ cũ chỉ để dùng hằng ngày. Nếu cần tái hiện lỗi lịch sử trên runtime Java 16, hãy giới hạn trong môi trường thử nghiệm cô lập, không đưa runtime hết hỗ trợ vào production và không để nó trở thành JDK mặc định của máy.

## 9. Các lựa chọn cần tránh khi học và triển khai

- **Không dùng JDK 16 làm môi trường mặc định:** dòng này đã hết vòng đời cập nhật. Chọn JDK LTS đang được hỗ trợ.
- **Không dùng `--enable-preview` cho tính năng đã chính thức ở Java 16:** records và pattern matching cho `instanceof` không cần cờ này.
- **Không học Sealed Classes theo trạng thái Java 16 như một tính năng final:** ở Java 16 nó vẫn là preview; phiên bản chính thức là Java 17 (JEP 409).
- **Không coi Vector API và Foreign-Memory Access API incubator của Java 16 là API ổn định:** nếu có nhu cầu hiện nay, tra trạng thái API trên JDK mục tiêu; Foreign Function & Memory API trở thành chính thức ở Java 22 (JEP 454).
- **Không nhầm `jlink` là tính năng mới của Java 16:** công cụ này đã có từ Java 9; `jpackage` mới là công cụ trở thành chính thức ở Java 16.
- **Không chỉ dùng `--source` và `--target` để khóa API:** dùng `--release` khi cần bảo đảm mã không gọi nhầm API mới hơn baseline.
- **Không cho rằng build thành công đồng nghĩa đã kiểm thử runtime:** vẫn cần test tích hợp, thư viện bên thứ ba, module, reflection, native library và đóng gói trên môi trường triển khai.

## 10. Checklist chọn JDK cho dự án

Trước khi bắt đầu hoặc nâng cấp dự án, hãy xác minh:

1. JDK được chọn còn nhận bản cập nhật bảo mật từ nhà cung cấp không?
2. Đây có phải LTS theo chính sách của nhà cung cấp không, và ngày hỗ trợ kết thúc là khi nào?
3. Phiên bản JDK có được framework, build tool, IDE và môi trường production hỗ trợ không?
4. Compiler thực tế có phải JDK đã chọn không (`javac --version`)?
5. Baseline Java/API có được khóa bằng `--release` không?
6. Runtime CI và production có đáp ứng baseline và các phụ thuộc không?
7. Quy trình cập nhật patch và kiểm thử bảo mật đã được xác định chưa?

## Tài liệu chính thức

- [Oracle Java SE Support Roadmap](https://www.oracle.com/java/technologies/java-se-support-roadmap.html) — lịch hỗ trợ Oracle JDK, trạng thái LTS/non-LTS và thời điểm hỗ trợ theo từng dòng.
- [Oracle Java Downloads](https://www.oracle.com/java/technologies/downloads/) — xác nhận bản JDK mới nhất và bản LTS mới nhất.
- [OpenJDK JDK Releases](https://ops.java/releases/?lang=en) — lịch phát hành và vòng đời các dòng JDK.
- [Eclipse Temurin Support](https://adoptium.net/support) — lịch duy trì và EOSL của các bản dựng Temurin.
- [Eclipse Temurin Downloads](https://adoptium.net/temurin/releases/) — chọn JDK theo phiên bản, hệ điều hành và kiến trúc.
- [JEP 395 — Records](https://openjdk.org/jeps/395) và [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394) — tính năng ngôn ngữ chính thức Java 16.
- [JEP 392 — Packaging Tool](https://openjdk.org/jeps/392) — `jpackage` trở thành công cụ chính thức.
- [Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/index.html) — kiểm tra API trên JDK LTS hiện đại.
- [The javac Command, JDK 25](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html) — cú pháp và hành vi tùy chọn `--release`.
- [JEP 397 — Sealed Classes (Second Preview)](https://openjdk.org/jeps/397) và [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409) — phân biệt preview Java 16 với tính năng chính thức Java 17.
- [JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454) — mốc chính thức của API native hiện đại.

**Nguyên tắc áp dụng:** Chọn JDK LTS đang được nhà cung cấp hỗ trợ làm môi trường học tập và phát triển. Ở thời điểm 27/11/2026, JDK 25 LTS là lựa chọn mặc định phù hợp; dùng `--release 16` để thực hành các tính năng Java 16 đã chính thức. Kiểm tra lịch hỗ trợ, bản cập nhật và yêu cầu của framework trước khi đưa JDK vào dự án thực tế.
