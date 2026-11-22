# Phân biệt lỗi ứng dụng cũ với thay đổi có chủ đích của nền tảng

Khi chuyển một ứng dụng từ JDK cũ sang JDK mới, việc “cùng mã nguồn nhưng kết quả khác” không tự động chứng minh JDK mới có lỗi. Kết quả khác có thể đến từ một thay đổi đã được Java Platform công bố; một bản sửa lỗi khiến hành vi vốn sai trước đây không còn xảy ra; một phụ thuộc ngoài JDK; hoặc chính ứng dụng lâu năm đã dựa vào một hành vi không được bảo đảm.

Đây là một vấn đề thường gặp trong **Java Advance Compatibility Migration**, đặc biệt ở nhóm **hành vi mặc định**: charset, locale, TLS, GC, quyền truy cập phản chiếu, thứ tự duyệt collection và cách đóng gói module có thể thay đổi giữa các bản phát hành. Nếu mọi khác biệt đều bị kết luận là “JDK regression”, đội ngũ dễ mất thời gian tìm lỗi sai chỗ hoặc cố giữ một hành vi cũ không còn an toàn. Ngược lại, nếu gán mọi vấn đề cho “thay đổi có chủ đích”, nhóm có thể bỏ sót lỗi thực sự trong JVM, thư viện hoặc ứng dụng.

Bài học trình bày cách lập luận dựa trên **hợp đồng hành vi**, thiết kế thí nghiệm đối chứng, phân loại nguyên nhân và lựa chọn hướng khắc phục có thể kiểm chứng. Mục tiêu không chỉ làm ứng dụng chạy lại, mà là phân biệt được **điều gì đã thay đổi**, **vì sao thay đổi**, và **ai cần sửa**.

## 1. Bốn câu hỏi phải tách riêng

Khi một ca kiểm thử thất bại sau nâng JDK, hãy đặt bốn câu hỏi:

1. **Quan sát được gì?** Kết quả, exception, hiệu năng, byte đầu ra hoặc hành vi nào khác trước?
2. **Hợp đồng đúng là gì?** Tài liệu API, đặc tả Java, tiêu chí nghiệp vụ hoặc giao thức bên ngoài yêu cầu điều gì?
3. **Thành phần nào làm thay đổi hành vi?** JDK, cấu hình, thư viện, hệ điều hành, dữ liệu, thời gian hay mã ứng dụng?
4. **Sự thay đổi đó có chủ đích và được hỗ trợ không?** Có tài liệu phát hành, JEP, đặc tả, issue đã sửa hoặc chính sách bảo mật làm bằng chứng không?

Một hiện tượng có thể mang **hai nhãn đúng cùng lúc**. Ví dụ, JDK tăng cường đóng gói các package nội bộ là thay đổi có chủ đích; nhưng ứng dụng cũ tự ý dùng deep reflection vào package đó cũng là một điểm yếu trong thiết kế ứng dụng. “Thay đổi có chủ đích” mô tả nguyên nhân ở nền tảng, còn “lỗi ứng dụng cũ” mô tả giả định sai trong phía consumer. Hai kết luận không nhất thiết loại trừ nhau.

## 2. Các nhóm nguyên nhân cần phân biệt

| Nhóm | Bản chất | Dấu hiệu điển hình | Ai thường xử lý? |
|---|---|---|---|
| Thay đổi nền tảng có chủ đích | JDK thay đổi hành vi mặc định, hỗ trợ API hoặc chính sách theo kế hoạch được công bố. | Có JEP, release notes, migration guide hoặc đặc tả mới. | Nhóm ứng dụng điều chỉnh mã/cấu hình, đôi khi cần thay thư viện. |
| Lỗi tiềm ẩn của ứng dụng bị phơi bày | Ứng dụng phụ thuộc hành vi không được cam kết hoặc tình cờ chạy được trước đây. | Dùng API nội bộ, dựa thứ tự không xác định, thiếu encoding/locale rõ ràng. | Nhóm ứng dụng. |
| Lỗi thực sự trong JDK hoặc bản update | JDK mới vi phạm một hợp đồng vẫn còn hiệu lực hoặc đưa vào một regression không mong muốn. | Reproducer nhỏ, có trường hợp đối chứng, khả năng liên quan đến bug tracker. | Nhà cung cấp JDK; ứng dụng có thể cần workaround tạm. |
| Thay đổi trong dependency/framework | Thư viện, plugin build, agent hoặc runtime phụ đã đổi API, thuật toán, transitive dependency. | Vấn đề chỉ xảy ra khi thay version thư viện hoặc cấu hình classpath. | Chủ sở hữu dependency và nhóm ứng dụng. |
| Khác biệt môi trường hoặc dữ liệu | OS, architecture, timezone, locale, certificate store, biến môi trường, file đầu vào khác. | Cùng JDK nhưng kết quả khác ở hai máy/container. | Nhóm cấu hình, vận hành hoặc quản trị dữ liệu. |
| Hành vi chưa được đặc tả đầy đủ | Kết quả cũ là một trong nhiều kết quả hợp lệ. | Tài liệu ghi “no guarantees”, “unspecified” hoặc không cam kết thứ tự/thời điểm. | Nhóm ứng dụng phải bỏ giả định không hợp lệ. |

Không nên sử dụng một nhãn như một phán quyết cảm tính. Mỗi kết luận cần có bằng chứng có thể lặp lại và đường dẫn đến hợp đồng bị ảnh hưởng.

## 3. Hợp đồng hành vi quan trọng hơn kết quả cũ

Một sai lầm phổ biến là lấy kết quả của ứng dụng trên JDK cũ làm *chân lý duy nhất*:

```text
JDK cũ trả A
JDK mới trả B
=> JDK mới sai
```

Suy luận này chưa đủ. Có ít nhất ba khả năng:

- Đặc tả yêu cầu A: B có thể là regression, nếu những biến khác đã được kiểm soát.
- Đặc tả cho phép cả A và B: ứng dụng dựa vào A đã phụ thuộc hành vi không được bảo đảm.
- Đặc tả hoặc chính sách đã thay đổi từ A sang B: cần xác định thay đổi có chủ đích và quy tắc migration.

**Hợp đồng có thể nằm ở nhiều tầng:**

| Tầng hợp đồng | Nguồn tham khảo | Ví dụ |
|---|---|---|
| Ngôn ngữ Java | Java Language Specification (JLS). | Quy tắc ép kiểu, evaluation order, checked exception. |
| JVM và class file | Java Virtual Machine Specification (JVMS). | Linkage, bytecode, class loading, exception của JVM. |
| API Java SE | Javadoc của đúng Java release. | Hợp đồng `List`, `Map`, `Charset`, `File`. |
| Chính sách nền tảng | JEP, release notes, migration guide, security guide. | Mặc định UTF-8, strong encapsulation, loại bỏ module. |
| Giao thức và dữ liệu | HTTP, TLS, JSON schema, định dạng file hoặc quy chuẩn nghiệp vụ. | Mã hóa file, chứng thư, format ngày giờ. |
| Hợp đồng ứng dụng | Yêu cầu sản phẩm, SLA, contract test, tài liệu API công ty. | Không được mất dữ liệu, chính sách làm tròn tiền. |

Khi phát hiện khác biệt, xác định tầng nào sở hữu yêu cầu trước khi quy lỗi. Một lớp Java đáp ứng Javadoc nhưng làm sai quy tắc nghiệp vụ vẫn là vấn đề ứng dụng. Ngược lại, một JVM làm sai hành vi đã được ngôn ngữ bảo đảm là ứng viên cho lỗi nền tảng.

## 4. “Unspecified”, “implementation-specific” và “undefined”

Không phải mọi hành vi quan sát được đều là một phần của hợp đồng. Trong tài liệu Java có những cách diễn đạt quan trọng:

- **Specified:** hành vi được đặc tả rõ; ứng dụng có thể dựa vào trong phạm vi điều kiện được nêu.
- **Unspecified:** đặc tả không cam kết một kết quả cụ thể trong những tình huống nhất định.
- **Implementation-specific:** cách triển khai có quyền chọn một chính sách hoặc giá trị cụ thể; có thể khác giữa vendor/version.
- **Deprecated/for removal:** API hoặc tính năng được thông báo không còn nên dùng và có thể bị loại theo lộ trình.

Ví dụ, `HashMap` không bảo đảm thứ tự iteration. Nếu một vòng lặp tình cờ trả phần tử theo đúng thứ tự ở JDK cũ, ứng dụng không thể coi đó là hợp đồng:

```java
import java.util.HashMap;
import java.util.Map;

public class AccidentalOrder {
    public static void main(String[] args) {
        Map<String, Integer> scores = new HashMap<>();
        scores.put("banana", 2);
        scores.put("apple", 1);
        scores.put("cherry", 3);

        scores.forEach((key, value) ->
                System.out.println(key + "=" + value));
    }
}
```

Đừng dùng output từng dòng của ví dụ trên làm golden result cho mọi JDK. Thứ tự không được bảo đảm; thay đổi thứ tự giữa các môi trường không tự chứng minh JDK mới sai.

Nếu cần thứ tự có ý nghĩa, sửa hợp đồng dữ liệu:

```java
Map<String, Integer> insertionOrder = new java.util.LinkedHashMap<>();
Map<String, Integer> sortedByKey = new java.util.TreeMap<>();
```

`LinkedHashMap` duy trì thứ tự chèn trong điều kiện dùng thông thường; `TreeMap` duy trì thứ tự theo comparator hoặc natural ordering. Chọn đúng container theo hợp đồng mong muốn thay vì khóa cứng một output tình cờ của `HashMap`.

## 5. Thiết kế thí nghiệm đối chứng để khoanh vùng nguyên nhân

Muốn biết JDK là nguyên nhân, phải giữ các biến khác càng ổn định càng tốt. So sánh ngẫu nhiên môi trường developer JDK 8 trên Windows với container Linux JDK 21 là không đủ: OS, locale, encoding, certificate store, data và phiên bản dependency cũng đã thay đổi.

Một ma trận đối chứng hữu ích:

| Thử nghiệm | Artifact | Runtime | Ý nghĩa |
|---|---|---|---|
| A — baseline | Bản đã phát hành trước đây | JDK cũ | Xác nhận hành vi đã biết. |
| B — đổi runtime | **Cùng file artifact** với A | JDK mới | Tách ảnh hưởng runtime; chỉ áp dụng khi bytecode và API còn chạy được. |
| C — biên dịch lại | Biên dịch lại cùng source/dependency | JDK mới | Xem ảnh hưởng compiler/toolchain và runtime mới. |
| D — đối chứng môi trường | Giữ artifact/JDK, thay từng cấu hình | Cùng JDK | Xác định timezone, encoding, provider, OS, cờ khởi động. |

Nếu B khác A nhưng C giống B, thay đổi nhiều khả năng nằm trong runtime hoặc dữ liệu/môi trường đi kèm. Nếu B giống A nhưng C khác, hãy kiểm tra compiler options, annotation processing, toolchain và dependency resolution. Đây chỉ là **giả thuyết khởi đầu**, không phải kết luận cuối cùng.

Đôi khi artifact cũ không chạy được trên JDK mới vì API bị loại; đôi khi artifact mới không thể chạy trên JDK cũ do class file version. Hãy ghi rõ ô nào “không áp dụng” thay vì cưỡng ép các phép so sánh không khả thi.

### 5.1. Khóa những biến dễ bị bỏ qua

Ít nhất nên ghi lại:

- Vendor, full version/build và kiến trúc JDK.
- OS và container/base image, kiến trúc CPU.
- Classpath/module path, dependency tree, Java agents và plugin build.
- JVM arguments, system properties và biến môi trường.
- Timezone, locale, default charset.
- TLS provider, truststore, security properties, certificate/keystore.
- Database, network endpoint, dữ liệu đầu vào, ngày/giờ, seed ngẫu nhiên.
- Số thread, mức tải, GC options, giới hạn CPU/memory và filesystem.

Không thu thập bí mật vào log công khai. Nếu cần so sánh cấu hình có chứa credential, hãy thay chúng bằng fingerprint hoặc chỉ lưu tên thuộc tính.

### 5.2. Những lệnh cơ bản

```bash
java -version
javac -version
java -XshowSettings:properties -version
```

Nếu dùng Maven:

```bash
mvn -version
mvn dependency:tree
```

Nếu dùng Gradle:

```bash
./gradlew --version
./gradlew dependencies
```

Trên Windows dùng `gradlew.bat` khi phù hợp. Các lệnh build trên chỉ nên được chạy trong quy trình điều tra thực tế với đúng module/configuration; không có nghĩa mọi dependency configuration đều được hiển thị giống nhau.

Nếu ứng dụng dùng container, phải kiểm tra `java -version` **bên trong container**. Version JDK trên máy host không xác định chắc runtime của tiến trình Java đang chạy.

## 6. Viết một reproducer tối thiểu

Một stack trace dài trong hệ thống production thường chứa nhiều lớp nhiễu. Reproducer tối thiểu là chương trình nhỏ chỉ thể hiện sự khác biệt cần giải thích.

Ví dụ, nếu file văn bản có ký tự tiếng Việt bị sai sau nâng JDK, đừng bắt đầu bằng toàn bộ quy trình import dữ liệu. Hãy tách hoạt động đọc/ghi byte:

```java
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

public final class CharsetReproducer {
    public static void main(String[] args) {
        String input = "Tiếng Việt";

        System.out.println("Default charset: "
                + Charset.defaultCharset());

        byte[] implicit = input.getBytes();
        byte[] explicit = input.getBytes(StandardCharsets.UTF_8);

        System.out.println("Implicit bytes: "
                + Arrays.toString(implicit));
        System.out.println("UTF-8 bytes: "
                + Arrays.toString(explicit));
    }
}
```

Chạy cùng class file trên hai runtime trong môi trường đối chứng, ghi lại charset mặc định và byte output. Nếu default charset khác, đã có một manh mối có thể kiểm chứng. Nhưng để kết luận nguyên nhân, còn phải xác nhận phiên bản JDK, hệ điều hành, cấu hình và dữ liệu gốc.

Một reproducer tốt có **input cố định**, **bước thực hiện rõ ràng**, **kết quả quan sát**, **kết quả theo hợp đồng mong đợi** và **phiên bản môi trường**. Nếu chỉ tái hiện bằng một ứng dụng lớn, mức tin cậy của kết luận thấp hơn.

## 7. Ví dụ: charset mặc định chuyển sang UTF-8

Một ví dụ rõ ràng của thay đổi có chủ đích là **JEP 400 — UTF-8 by Default**. Từ JDK 18, UTF-8 là default charset chuẩn cho các API Java SE phụ thuộc vào charset mặc định, thay vì phụ thuộc vào locale/hệ điều hành theo cách trước đây. Một số cơ chế cấu hình tương thích đặc thù vẫn tồn tại; không nên suy ra rằng mọi thiết bị đầu cuối hoặc mọi API I/O đều có encoding hoàn toàn giống nhau.

### 7.1. Hiện tượng

Ứng dụng cũ ghi:

```java
String content = "Hóa đơn";
byte[] bytes = content.getBytes();
```

Hoặc đọc:

```java
String content = Files.readString(path);
```

**Lưu ý:** `Files.readString(Path)` từ Java 11 mặc định dùng UTF-8 theo API, không giống `new String(byte[])` hoặc `String.getBytes()` dùng default charset. Khi điều tra, phải xác định đúng overload và hợp đồng của từng API, không gom mọi lời gọi I/O thành “dùng charset mặc định”.

Với `String.getBytes()` hoặc `new String(byte[])`, nếu ở môi trường cũ charset mặc định là một encoding không phải UTF-8, cách biểu diễn byte có thể khác khi chạy trên JDK 18+. File legacy được ghi theo encoding cũ có thể bị giải mã sai nếu chương trình đọc bằng mặc định mới.

### 7.2. Căn cứ phân loại

- Có JEP 400 công bố thay đổi có chủ đích.
- Ứng dụng đã phụ thuộc vào charset mặc định mà không ghi rõ trong hợp đồng file.
- Khác biệt xuất hiện có điều kiện theo encoding cũ, cấu hình và dữ liệu đầu vào.

Kết luận phù hợp: **thay đổi có chủ đích của nền tảng làm lộ một giả định ngầm trong ứng dụng**.

### 7.3. Cách khắc phục bền vững

Chọn encoding chính xác theo định dạng dữ liệu và chỉ định tường minh:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public final class TextIO {
    public static void save(Path file, String content)
            throws java.io.IOException {
        Files.writeString(file, content, StandardCharsets.UTF_8);
    }

    public static String load(Path file)
            throws java.io.IOException {
        return Files.readString(file, StandardCharsets.UTF_8);
    }
}
```

Nếu file hiện tại thực sự dùng một encoding legacy, hãy đọc theo encoding đó và có kế hoạch chuyển đổi format. Không ép đọc mọi dữ liệu cũ là UTF-8 nếu byte gốc không tuân theo UTF-8.

Biện pháp tương thích như `-Dfile.encoding=COMPAT` trên JDK hỗ trợ tùy chọn này có thể giúp kiểm tra hoặc chuyển tiếp, nhưng không nên trở thành hợp đồng dữ liệu lâu dài. Tài liệu và hành vi hỗ trợ của property có thể thay đổi theo release, nên ưu tiên explicit charset trong code và format.

## 8. Ví dụ: strong encapsulation của JDK internal APIs

Các bản JDK hiện đại giới hạn việc truy cập trực tiếp vào package và thành viên nội bộ. JEP 261 giới thiệu JPMS ở JDK 9; JEP 396 tăng cường strong encapsulation mặc định ở JDK 16; JEP 403 củng cố việc này từ JDK 17 bằng cách loại bỏ cơ chế cho phép nới lỏng trên diện rộng bằng `--illegal-access`.

### 8.1. Hiện tượng

Code cũ sử dụng deep reflection:

```java
import java.lang.reflect.Field;

public final class InternalFieldAccess {
    public static void main(String[] args) throws Exception {
        Field value = String.class.getDeclaredField("value");
        value.setAccessible(true);
        System.out.println(value.getType());
    }
}
```

Khi chạy trên JDK có strong encapsulation và không có quyền mở package phù hợp, `setAccessible(true)` có thể ném `java.lang.reflect.InaccessibleObjectException`. Một số bản cũ từng cho phép hoặc cảnh báo rồi vẫn cho truy cập; điều đó không biến chi tiết nội bộ `String.value` thành API công khai.

### 8.2. Căn cứ phân loại

- JPMS và strong encapsulation là thay đổi nền tảng có chủ đích, được công bố.
- Mã ứng dụng dựa vào cấu trúc private của một class JDK.
- Quy tắc public API của `String` không bảo đảm tên, kiểu hay khả năng truy cập field này.

Kết luận: **lỗi thiết kế phụ thuộc internals trong ứng dụng, được bộc lộ bởi chính sách đóng gói nền tảng**.

### 8.3. Xử lý

Thay thao tác phản chiếu bằng API công khai nếu có. Nếu thư viện ngoài gây lỗi, ưu tiên nâng thư viện đã sửa tương thích JDK mới.

Trong giai đoạn chuyển tiếp, có thể mở **một package cụ thể** cho một target module:

```bash
java --add-opens java.base/java.lang=ALL-UNNAMED \
     -cp app.jar com.example.Main
```

Ví dụ này chỉ áp dụng khi consumer là mã trên classpath (unnamed module). Với named module, cần dùng tên module đích thực tế thay cho `ALL-UNNAMED`. `--add-opens` chỉ nới quyền phản chiếu cho package được chỉ định, không bảo đảm API nội bộ ổn định. Không dùng nó như giải pháp lâu dài hoặc mở hàng loạt package một cách tùy tiện.

## 9. Ví dụ: thứ tự duyệt collection thay đổi

Giả sử hệ thống phát sinh chữ ký số từ chuỗi nối các phần tử của `HashMap`:

```java
StringBuilder payload = new StringBuilder();
for (String key : map.keySet()) {
    payload.append(key).append('=').append(map.get(key)).append('&');
}
String signatureInput = payload.toString();
```

Nếu chương trình ký payload theo thứ tự iteration, một thay đổi thứ tự khi JDK, số lượng phần tử, cách hash hoặc dữ liệu khác sẽ làm chữ ký khác. Nhưng `HashMap` không cam kết thứ tự; ứng dụng đã đặt yêu cầu ổn định trên một thuộc tính không được bảo đảm.

**Phân loại:** vấn đề tương thích do giả định sai ở ứng dụng. Có thể có thay đổi implementation trong nền tảng, nhưng không cần chứng minh “JDK cố tình đổi thứ tự” mới xác định được lỗi hợp đồng.

**Khắc phục:** xác định canonical ordering (ví dụ sắp xếp key bằng comparator được chuẩn hóa) trước khi serialization và ký:

```java
import java.util.Map;
import java.util.TreeMap;

Map<String, String> ordered = new TreeMap<>(map);
StringBuilder payload = new StringBuilder();

ordered.forEach((key, value) -> {
    payload.append(key).append('=').append(value).append('&');
});
```

Trong hệ thống thực, cần quy định cả escape ký tự, dấu phân cách, Unicode normalization, cách biểu diễn `null` và thứ tự key. Chỉ đổi `HashMap` sang `TreeMap` có thể chưa đủ nếu giao thức ký không xác định canonical format.

## 10. Ví dụ: module Java EE và CORBA không còn đi kèm JDK

JEP 320 loại bỏ một số Java EE và CORBA modules khỏi JDK 11, trong đó có JAXB. Một ứng dụng sử dụng:

```java
import javax.xml.bind.JAXBContext;
```

có thể không biên dịch hoặc chạy được trên JDK 11+ nếu artifact không mang dependency cần thiết.

Đây là **thay đổi đóng gói nền tảng có chủ đích**, không có nghĩa JDK compiler “không còn hỗ trợ XML” hay Java mất toàn bộ thư viện XML. Ứng dụng phải khai báo dependency JAXB phù hợp hoặc chuyển sang stack/API được hỗ trợ, kiểm tra tương thích giữa namespace `javax.xml.bind` và `jakarta.xml.bind` theo phiên bản framework đang dùng.

Cách điều tra:

1. Tìm import, reflective reference và dependency liên quan đến JAXB.
2. Đọc JEP 320 cùng migration guide của JDK đích.
3. Kiểm tra `mvn dependency:tree` hoặc báo cáo Gradle để biết artifact có JAXB API và implementation không.
4. Chọn dependency tương thích với cả framework và baseline JDK.
5. Chạy integration test cho marshalling/unmarshalling, schema và exception mapping.

Không phải lỗi nào báo `ClassNotFoundException` cũng do module bị loại; cần đối chiếu chính xác class name, classloader và classpath/module path.

## 11. Ví dụ: TLS và thuật toán bảo mật bị giới hạn

Một ứng dụng kết nối HTTPS có thể hoạt động trên bản JDK update cũ nhưng thất bại sau cập nhật với `SSLHandshakeException`. Không nên lập tức kết luận HTTP client trong JDK mới bị lỗi.

Có thể có nhiều nguyên nhân:

- Bản cập nhật JDK vô hiệu hóa một thuật toán, cipher suite, protocol hoặc key size không còn an toàn.
- Server dùng cấu hình TLS cũ, chứng thư hết hạn hoặc chuỗi chứng thư không hợp lệ.
- Truststore hoặc certificate authority khác giữa hai môi trường.
- Proxy, middlebox hoặc load balancer gửi handshake khác dự kiến.
- Thư viện HTTP/client hoặc bảo mật được nâng cùng lúc.
- Có regression thực sự trong TLS provider, nhưng cần bằng chứng.

Trong JDK, các security properties như `jdk.tls.disabledAlgorithms` và `jdk.certpath.disabledAlgorithms` có thể ảnh hưởng việc đàm phán TLS và xác minh chứng thư. Những chính sách này có thể thay đổi ở cả bản update, không chỉ khi đổi feature release.

Một cách điều tra an toàn:

1. Ghi đầy đủ version/build JDK và cấu hình TLS client/server.
2. Kiểm tra certificate chain, ngày hết hạn, hostname và truststore.
3. Đối chiếu release notes và security properties ở hai bản JDK.
4. Tái hiện với một server test do nhóm kiểm soát, không chỉ production endpoint.
5. Thử sửa server dùng protocol/cipher còn được hỗ trợ.

**Không nên** vô hiệu hóa hostname verification, bỏ kiểm tra chứng thư hay bật lại thuật toán yếu trong production chỉ để “chứng minh JDK có lỗi”. Nếu cần workaround tạm, phải có phê duyệt an ninh, giới hạn phạm vi và thời điểm loại bỏ rõ ràng.

## 12. Ví dụ: locale, timezone và dữ liệu văn hóa

Code sau phụ thuộc vào locale mặc định:

```java
String normalized = input.toUpperCase();
```

Kết quả có thể khác giữa những locale nhất định, chẳng hạn các quy tắc chuyển chữ hoa có liên quan tới tiếng Thổ Nhĩ Kỳ. Vấn đề có thể xuất hiện khi container/JDK thay locale mặc định, ngay cả khi Java source không thay.

Với mã định danh, tên protocol, enum token hoặc key không phải ngôn ngữ tự nhiên, thường nên dùng:

```java
import java.util.Locale;

String normalized = input.toUpperCase(Locale.ROOT);
```

Với văn bản hiển thị cho người dùng, hãy dùng `Locale` được chọn theo người dùng hoặc yêu cầu nghiệp vụ; không luôn chọn `Locale.ROOT`.

Ngoài biến môi trường, Java đã thay đổi cách dùng locale data qua các release; JEP 252 đưa CLDR thành nguồn locale data mặc định từ JDK 9. Một khác biệt định dạng ngày/tháng, tên ngôn ngữ hoặc dấu phân cách có thể xuất phát từ chính sách dữ liệu locale mới, phiên bản CLDR hoặc cấu hình locale.

**Phân loại cần dựa vào nguồn thay đổi cụ thể:** chỉ thấy chuỗi ngày khác chưa đủ để nói “JDK intentional change”. Phải kiểm tra locale input, timezone, formatter, provider và dữ liệu locale. Nếu business contract yêu cầu format cố định, hãy chọn formatter và locale tường minh, thay vì khóa output của một môi trường tình cờ.

## 13. Ví dụ: thay đổi GC và hiệu năng mặc định

JEP 248 đặt G1 thành default garbage collector trên JDK 9 cho nhiều cấu hình server-class. Khi chuyển từ JDK cũ, mức sử dụng CPU, thời gian pause, heap behavior hoặc throughput có thể khác ngay cả khi code và dữ liệu giống nhau.

Nhưng hiệu năng thay đổi không tự động là lỗi JVM:

- GC mặc định có thể thay đổi có chủ đích.
- Heuristics, JIT compilation, tiered compilation hoặc container awareness có thể được điều chỉnh.
- Cờ JVM cũ có thể bị đổi, deprecated hoặc loại bỏ.
- Container CPU/memory limit có thể khác, dẫn tới khác heap hoặc parallelism.
- Thread scheduling, I/O, database response và tải thực tế có thể khác.

Để tìm nguyên nhân, đo thông số theo cùng kịch bản tải: throughput, latency P50/P95/P99, pause time, allocation rate, heap và CPU. Ghi nhận GC thực tế bằng logging/metrics phù hợp với JDK đích.

Với Unified JVM Logging trong các JDK hiện đại, một ví dụ có thể là:

```bash
java -Xlog:gc*:file=gc.log:time,level,tags \
     -jar app.jar
```

Không khôi phục hàng loạt JVM flags từ cấu hình cũ trước khi có số đo. Việc ép lại GC cũ có thể giữ một vài đặc điểm hiệu năng nhưng không nhất thiết là giải pháp tối ưu hay được hỗ trợ về lâu dài.

## 14. Khi nào nên nghi ngờ bug thực sự trong JDK?

Một bug JDK đáng nghi hơn khi có nhiều dấu hiệu:

- Có **hợp đồng vẫn còn hiệu lực** và JDK mới dường như vi phạm hợp đồng đó.
- Reproducer nhỏ, độc lập với ứng dụng lớn và có input cố định.
- Cùng artifact/source trên nhiều bản JDK thể hiện ranh giới regression rõ ràng.
- Kết quả không thể giải thích bằng cấu hình, data, dependency, locale, OS hoặc quyền truy cập thay đổi.
- Không có tài liệu phát hành hoặc thay đổi đặc tả nào cho phép kết quả mới.
- Có issue tương ứng trong JDK Bug System, hoặc lỗi tái hiện trên bản update khác với dữ liệu đáng tin.

Ví dụ giả định: một phương thức Java SE có Javadoc yêu cầu trả kết quả X cho input Y, nhưng trong một bản JDK cụ thể trả Z, còn các bản trước/sau trả X. Nếu reproducer độc lập và kiểm soát đủ biến, đó là một ứng viên bug thực sự.

**Cảnh báo:** Việc một release note không nhắc đến khác biệt không đủ để kết luận JDK bị lỗi. Có thể còn một hành vi không được bảo đảm, một thay đổi trong dependency hoặc một fix được phát hành nhưng chưa được tìm thấy. Hãy giữ trạng thái điều tra là “chưa xác định” cho tới khi có bằng chứng đủ mạnh.

### 14.1. Đóng gói báo cáo bug có thể hành động

Một báo cáo tốt thường có:

```text
Title: [JDK version] Contract violation in [API/component]

Environment:
  JDK vendor and full build:
  OS / architecture:
  JVM arguments:
  Dependencies:

Minimal reproducer:
  Exact source:
  Build command:
  Run command:

Expected:
  Behavior according to specification/API contract:

Actual:
  Output / exception / trace:

Comparison:
  Known working JDK build:
  Known failing JDK build:
  Other controlled observations:

References:
  Javadoc / JLS / JVMS:
  Release notes / JEP / related JBS issue:
```

Không đưa secrets, production database hoặc thông tin khách hàng vào reproducer công khai.

## 15. Cây quyết định khi thấy hành vi khác

```text
           Ứng dụng khác hành vi sau nâng JDK?
                          |
                          v
                 Có tái hiện được không?
                   /               \
                 Không              Có
                  |                  |
         Thu thập thêm dữ liệu       v
                             Đã cố định môi trường,
                             artifact, input chưa?
                               /          \
                             Chưa          Rồi
                              |             |
                         Tạo đối chứng      v
                                    Hợp đồng cho kết quả gì?
                                      /             \
                               Không cam kết         Có cam kết
                                    |                  |
                             Sửa giả định            v
                             của ứng dụng     Có thay đổi nền tảng
                                               được công bố không?
                                                 /         \
                                               Có          Chưa rõ
                                                |            |
                                         Đánh giá migration  v
                                                       Tối giản reproducer,
                                                       kiểm tra JBS và vendor
```

Cây quyết định chỉ là công cụ điều tra. Có thể phải quay lại các bước trước khi tìm thêm biến môi trường chưa kiểm soát hoặc phát hiện bug ở thư viện thay vì JDK.

## 16. Làm việc với tài liệu phát hành và nguồn chứng cứ

Khi cần xác nhận một khác biệt là chủ đích, nên đối chiếu các nguồn theo thứ tự phù hợp:

1. **Javadoc/JLS/JVMS của release đích** để xác định hợp đồng.
2. **JEP** cho những thay đổi nền tảng lớn như UTF-8 mặc định, JPMS hoặc encapsulation.
3. **Release notes và migration guide** cho cả feature release lẫn update release.
4. **JDK Bug System (JBS)** để tìm regression, bug fix, CSR và trạng thái fix.
5. **Tài liệu nhà cung cấp JDK** nếu dùng build/vender có bản vá hoặc chính sách hỗ trợ khác.
6. **Changelog dependency** nếu ứng dụng nâng framework, driver hoặc plugin cùng lúc.

Không gộp mọi thay đổi dưới cụm “Java 17 khác Java 8”. Nhiều thay đổi xuất hiện lần lượt ở JDK 9, 11, 16, 17 hoặc 18; một số chỉ xảy ra trong bản update. Xác định **mốc bắt đầu thay đổi** giúp giải thích nguyên nhân và chọn hướng xử lý.

Một cách ghi nhận evidence:

| Mã chứng cứ | Nguồn | Điều nó chứng minh | Giới hạn |
|---|---|---|---|
| E1 | Java API Javadoc | Hợp đồng của phương thức. | Có thể không mô tả mọi cấu hình môi trường. |
| E2 | JEP / release note | Thay đổi có chủ đích hoặc bug fix được công bố. | Không thay thế thử nghiệm trên application cụ thể. |
| E3 | Reproducer A/B | Hành vi khác theo runtime dưới điều kiện đã kiểm soát. | Chỉ chứng minh điều kiện được thử. |
| E4 | Log / heap / GC / TLS trace | Dấu vết kỹ thuật khi thất bại. | Có thể thiếu thông tin từ dependency khác. |
| E5 | Contract test | Hành vi nghiệp vụ đúng/sai. | Test phải bắt nguồn từ yêu cầu thực, không chỉ output cũ. |

**Nguyên tắc:** Một release note xác nhận lý do thay đổi; nó không tự khẳng định ứng dụng xử lý đúng hay sai. Reproducer chứng minh hiện tượng; đặc tả và hợp đồng quyết định tiêu chí đúng.

## 17. Đừng “sửa” thay đổi chủ đích bằng cách vô hiệu hóa bảo vệ

Khi thấy ứng dụng lỗi, một số cách sửa nóng hấp dẫn:

- Mở tất cả package nội bộ bằng nhiều `--add-opens`.
- Bật lại cipher/TLS algorithm yếu hoặc bỏ certificate validation.
- Giữ `file.encoding` theo máy mà không định nghĩa format dữ liệu.
- Ghim JDK cũ không được cập nhật bảo mật.
- Nuốt exception để integration test xanh.
- Cố định thứ tự kết quả tình cờ bằng một snapshot test.

Những biện pháp này có thể biến lỗi hiển thị thành rủi ro âm thầm. Một workaround tạm chỉ nên được chấp nhận khi:

1. Đã xác định rõ nguyên nhân và ảnh hưởng.
2. Có phạm vi áp dụng nhỏ nhất có thể.
3. Có phê duyệt đối với rủi ro bảo mật/vận hành liên quan.
4. Có test xác nhận workaround không làm đổi hợp đồng nghiệp vụ.
5. Có ticket, owner và ngày dự kiến loại bỏ.

Nếu cần rollback JDK để giữ production ổn định, vẫn phải đánh giá tác động security và thời gian hỗ trợ của bản rollback. Rollback là biện pháp vận hành, không tự là lời giải thích kỹ thuật.

## 18. Khi hợp đồng ứng dụng phải thay đổi cùng nền tảng

Đôi khi nền tảng thay đổi có chủ đích, và ứng dụng cần **chủ động thay đổi hợp đồng** thay vì duy trì hành vi cũ bằng mọi giá.

Ví dụ:

- File định dạng legacy được chuyển đổi vĩnh viễn sang UTF-8 và tăng format version.
- Plugin dùng internal API được thay bằng API công khai hoặc SPI ổn định.
- Server bắt buộc TLS hiện đại, client cũ phải được nâng.
- API nghiệp vụ đang trả collection “theo thứ tự HashMap” được chuẩn hóa thành thứ tự rõ ràng.

Khi thay hợp đồng, cần lập kế hoạch phiên bản dữ liệu và tương thích hai chiều:

| Câu hỏi | Ví dụ câu trả lời cần quyết định |
|---|---|
| Dữ liệu cũ vẫn được đọc không? | Có, qua bộ đọc legacy dùng charset đã xác định. |
| Dữ liệu mới có cần đọc được bằng phiên bản app cũ không? | Nếu rollout cuốn chiếu, có thể cần compatibility window. |
| Có cần feature flag để chuyển dần? | Có, nếu chưa thể chuyển toàn bộ dữ liệu cùng lúc. |
| Client bên ngoài có cần thông báo? | Có, nếu API hoặc format mới làm thay đổi kết quả. |
| Khi rollback, dữ liệu mới xử lý thế nào? | Phải có quy trình rollback hoặc cơ chế dual-read. |

Một migration thành công không phải lúc nào cũng là giữ mọi output cũ. Nó phải giữ **những cam kết cần giữ**, đồng thời cập nhật những cam kết được thay đổi có kiểm soát.

## 19. Kiểm thử để phân biệt regression với deliberate change

Không nên viết mọi test kiểu “assert bằng output của JDK cũ”. Cần phân ba lớp test:

### 19.1. Contract tests

Mô tả điều mà API hoặc nghiệp vụ phải làm, bất kể runtime:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;

class ExportEncodingTest {
    @Test
    void exportsUtf8IndependentlyOfDefaultCharset() {
        byte[] bytes = "Việt Nam"
                .getBytes(StandardCharsets.UTF_8);

        assertEquals(
                "Việt Nam",
                new String(bytes, StandardCharsets.UTF_8));
    }
}
```

Đây là một ví dụ đơn giản minh họa hợp đồng explicit charset. Trong hệ thống thực, test phải gọi chính code xuất dữ liệu của ứng dụng, thay vì chỉ kiểm tra API chuẩn riêng lẻ.

### 19.2. Characterization tests

Ghi lại hành vi cũ để hiểu hiện trạng và hỗ trợ migration, nhưng **chưa mặc định** đó là hành vi đúng. Ví dụ, ghi nhận byte gốc của một file legacy hoặc cách chương trình tạo signature trước khi đổi format.

Khi xác định khác biệt do hành vi không được bảo đảm, hãy cập nhật test thành contract test cho hành vi mong muốn. Không cố buộc JDK mới sinh đúng thứ tự hoặc thời điểm không được đặc tả.

### 19.3. Cross-runtime tests

Chạy cùng bộ contract test trên các JDK được sản phẩm hỗ trợ:

```text
Test suite / fixtures
      |
      +--> JDK baseline
      |
      +--> JDK target
      |
      +--> JDK update mới (nếu cần)
                 |
                 v
     So sánh theo contract + metadata
```

Không nên coi test thất bại trên JDK mới là thất bại của migration nếu test đang áp đặt một hành vi vô tình của JDK cũ. Khi thay đổi hợp đồng có chủ đích, cập nhật expected result cùng migration note và chứng cứ liên quan.

## 20. Một mẫu hồ sơ phân loại sự cố

Có thể ghi cho từng issue:

```yaml
incident: MIG-JDK-042
title: "CSV import đọc sai dấu tiếng Việt"
affectedFlow: "Import hồ sơ khách hàng"
baselineRuntime: "JDK cũ và build cụ thể"
targetRuntime: "JDK mới và build cụ thể"
artifact: "Checksum hoặc mã bản phát hành"
input: "File fixture đại diện đã loại dữ liệu nhạy cảm"
expectedContract: "CSV legacy dùng encoding được quy định"
observedOld: "Đọc đúng"
observedNew: "Một số ký tự bị thay thế"
controlledDifference: "Default charset đổi"
platformEvidence: "JEP 400 và release notes liên quan"
classification: "Intentional platform change + implicit app assumption"
remediation: "Đọc/ghi với charset tường minh; chuyển đổi dữ liệu legacy"
owner: "Nhóm import dữ liệu"
verification: "Contract test chạy trên cả runtime nguồn và đích"
status: "Đang khắc phục"
```

Các giá trị trong ví dụ là dữ liệu minh họa. Hồ sơ thực phải ghi chính xác version/build và link chứng cứ cụ thể; không chép các mô tả chung vào báo cáo rồi coi như đã xác định nguyên nhân.

Một sự cố có thể có nhiều contributing factors. Nên có trường **confidence** hoặc **hypothesis status** như “giả thuyết”, “đã tái hiện”, “đã đối chiếu đặc tả”, “đã xác nhận nguyên nhân” để tránh chuyển kết luận tạm thành sự thật.

## 21. Phân biệt thay đổi của platform và thay đổi do cách triển khai

Một hành vi có thể thay đổi vì runtime được cấu hình theo cách khác, không nhất thiết vì Java SE đã đổi hợp đồng.

Ví dụ, hai bản JDK cùng feature release nhưng khác vendor có thể dùng security provider hoặc chuỗi bản vá khác nhau. Hai container cùng chạy JDK 21 có thể có timezone database, truststore hoặc system locale khác. Một JDK update có thể sửa lỗi TLS trong khi mã ứng dụng và feature release vẫn giữ nguyên.

Vì vậy, trong báo cáo nên tách:

- **Spec change:** đặc tả hoặc chính sách công khai thay đổi.
- **Implementation change:** implementation được đổi nhưng có thể vẫn nằm trong hợp đồng cũ.
- **Runtime configuration change:** flags/properties/providers thay đổi.
- **Distribution difference:** vendor/build khác.
- **Application/dependency change:** mã hoặc artifact trong ứng dụng khác.

Không gán chung nhãn “JDK upgrade” cho tất cả. Nêu rõ mốc thay đổi và liên hệ với giả định của ứng dụng sẽ giúp nhóm quyết định cần sửa code, sửa cấu hình, nâng dependency hay báo bug cho vendor.

## 22. Những cách suy luận sai thường gặp

**“Ngày trước chạy được nên JDK mới phải sai.”** Trước hết kiểm tra hợp đồng. Hành vi cũ có thể chưa được bảo đảm hoặc là lỗi vốn tồn tại lâu.

**“Có JEP là khỏi cần điều tra.”** JEP mô tả chủ đích, nhưng không chứng minh mọi lỗi quan sát được đều do JEP ấy gây ra.

**“Chỉ cần sửa test kỳ vọng theo output mới.”** Có thể đang chấp nhận kết quả sai nghiệp vụ. Test phải dựa trên contract, không chỉ làm xanh pipeline.

**“Cùng class file thì chỉ JDK mới là biến duy nhất.”** OS, container, dữ liệu, module path và security properties cũng có thể khác.

**“Compile thành công nghĩa là runtime compatible.”** Runtime có thể thiếu class, chặn reflection, yêu cầu provider mới hoặc cho output khác.

**“Một lỗi chỉ xuất hiện khi nâng JDK chắc chắn là JVM bug.”** Điều kiện kích hoạt có thể là cách JDK mới xử lý đúng một hợp đồng vốn bị vi phạm ở ứng dụng.

**“Đổi một flag là migration xong.”** Flag có thể là workaround tạm và không thay được việc loại bỏ phụ thuộc nội bộ hoặc format ngầm.

**“Không có lỗi exception thì hành vi đúng.”** Sai lệch encoding, thứ tự, timezone hay số liệu có thể gây lỗi dữ liệu âm thầm.

## 23. Quy trình điều tra áp dụng cho dự án thực

### Bước 1: Ghi nhận triệu chứng và mức ảnh hưởng

Phân biệt lỗi startup, compile, runtime exception, sai dữ liệu, hiệu năng hay bảo mật. Xác định tác động tới người dùng và hệ thống bên ngoài.

### Bước 2: Thu thập baseline có thể lặp lại

Lưu JDK version/build, artifact checksum, dependency graph, JVM args, env, input fixture và expected contract.

### Bước 3: Thực hiện thử nghiệm đối chứng

Chạy cùng artifact trên runtime nguồn/đích nếu khả thi. Thay từng biến, không nâng đồng thời cả JDK, framework, OS và cấu hình khi chưa có baseline.

### Bước 4: Tạo reproducer tối thiểu

Tách code dùng API liên quan, ghi input và output, kiểm tra error class/stack trace và tránh phụ thuộc hệ thống ngoài.

### Bước 5: Xác định hợp đồng

Đọc Javadoc/JLS/JVMS, tài liệu giao thức, yêu cầu nghiệp vụ và các lời hứa tương thích với client.

### Bước 6: Tìm chứng cứ thay đổi nền tảng

Đối chiếu JEP, release notes, migration guide và bug tracker tại đúng mốc version/update.

### Bước 7: Gán phân loại có mức độ tin cậy

Chọn một hoặc nhiều nhóm nguyên nhân, ghi rõ phần đã xác nhận và giả thuyết cần kiểm chứng. Nếu chưa đủ thông tin, giữ trạng thái chưa xác định.

### Bước 8: Chọn phương án sửa bền vững

Ưu tiên API công khai, cấu hình tường minh, dependency được hỗ trợ, contract test và migration dữ liệu có version. Dùng workaround tạm với điều kiện và owner rõ ràng.

### Bước 9: Kiểm thử và triển khai có kiểm soát

Chạy regression/integration test trên runtime mục tiêu, đo hiệu năng và theo dõi dấu hiệu lỗi dữ liệu âm thầm. Lập kế hoạch rollback nếu cần.

### Bước 10: Lưu quyết định

Ghi lại mốc JDK, bằng chứng, phân loại và tiêu chí chấp nhận. Tài liệu này giúp những lần migration sau không lặp lại cuộc điều tra tương tự.

## 24. Checklist trước khi chốt “lỗi JDK” hay “thay đổi có chủ đích”

- [ ] Đã xác định triệu chứng chính xác, không chỉ mô tả “ứng dụng lỗi sau nâng cấp”.
- [ ] Đã ghi version, vendor và build của cả JDK nguồn lẫn đích.
- [ ] Đã xác định artifact/source/dependency và các flags đang chạy.
- [ ] Đã kiểm soát input, OS, timezone, locale, charset, certificate và môi trường cần thiết.
- [ ] Đã biết hành vi nào được hợp đồng công khai hoặc nghiệp vụ cam kết.
- [ ] Đã phân biệt hành vi specified với unspecified/implementation-specific.
- [ ] Đã thử một reproducer tối thiểu hoặc thí nghiệm đối chứng tương đương.
- [ ] Đã kiểm tra JEP/release notes/migration guide ở đúng phiên bản.
- [ ] Đã kiểm tra khả năng bug trong JDK, dependency và cấu hình môi trường.
- [ ] Đã ghi mức độ tin cậy của kết luận và phần chưa được xác minh.
- [ ] Đã thiết kế sửa lỗi dựa trên contract thay vì giữ output cũ vô điều kiện.
- [ ] Đã có test cho dữ liệu, bảo mật và hiệu năng phù hợp.
- [ ] Workaround tạm, nếu có, đã được giới hạn phạm vi và có kế hoạch loại bỏ.
- [ ] Đã lưu migration note và thông tin phục vụ điều tra lần sau.

## Tài liệu tham khảo

- [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): thay đổi về charset mặc định từ JDK 18.
- [JEP 261 — Module System](https://openjdk.org/jeps/261): nền tảng JPMS từ JDK 9.
- [JEP 396 — Strongly Encapsulate JDK Internals by Default](https://openjdk.org/jeps/396): strong encapsulation mặc định từ JDK 16.
- [JEP 403 — Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403): tăng cường giới hạn truy cập JDK internals ở JDK 17.
- [JEP 320 — Remove the Java EE and CORBA Modules](https://openjdk.org/jeps/320): loại bỏ các module cũ khỏi JDK 11.
- [JEP 252 — Use CLDR Locale Data by Default](https://openjdk.org/jeps/252): thay đổi nguồn dữ liệu locale mặc định từ JDK 9.
- [JEP 248 — Make G1 the Default Garbage Collector](https://openjdk.org/jeps/248): thay đổi default GC ở JDK 9.
- [Oracle Java SE Migration Guides](https://docs.oracle.com/en/java/javase/): migration guides và release documentation theo JDK cụ thể.
- [Java Language Specification](https://docs.oracle.com/javase/specs/jls/se21/html/index.html): hợp đồng ngôn ngữ Java.
- [Java Virtual Machine Specification](https://docs.oracle.com/javase/specs/jvms/se21/html/index.html): hợp đồng JVM và class file.
- [JDK Bug System](https://bugs.openjdk.org/): bug reports, fixes và issue liên quan đến regression.

## Kết luận

Khác biệt sau khi nâng JDK không thể được phân loại chỉ bằng việc so sánh hai output. Cần biết hợp đồng nào đang được thực hiện, phiên bản nền tảng nào thay đổi, yếu tố môi trường nào khác và bằng chứng nào xác nhận một thay đổi có chủ đích. Default charset UTF-8, strong encapsulation, module removal hoặc chính sách TLS có thể khiến các giả định ngầm của ứng dụng cũ lộ rõ; trong khi một hành vi vi phạm đặc tả vẫn có thể là bug JDK thực sự. Cách xử lý đáng tin cậy là tạo baseline có thể tái hiện, kiểm tra JEP/Javadoc/release notes, phân loại với mức độ chắc chắn rõ ràng và sửa theo contract được hỗ trợ. Mục tiêu của migration không phải bảo toàn mọi thói quen của JDK cũ, mà là giữ các cam kết đúng và thích nghi có kiểm soát với nền tảng mới.
