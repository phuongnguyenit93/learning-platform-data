# Tránh phụ thuộc vào tên suy ra từ tên tệp JAR

Khi một JAR chưa có `module-info.class` được đặt trên module path, JPMS có thể coi nó là một automatic module. Nếu manifest không khai báo `Automatic-Module-Name`, JDK suy ra tên mô-đun từ tên tệp JAR. Tên này có thể thay đổi khi hệ thống build đổi tên artifact, thêm classifier hoặc điều chỉnh quy ước phát hành. Mọi named module đang khai báo `requires` theo tên cũ có thể không còn resolve được dependency.

Với thư viện chưa sẵn sàng có module descriptor tường minh, cách phù hợp là công bố tên ổn định bằng `Automatic-Module-Name`. Consumer khi đó phụ thuộc vào tên mô-đun đã được chọn làm hợp đồng, thay vì phụ thuộc vào cách artifact được đặt tên trong từng lần build.

## 1. Tên mô-đun và tên tệp JAR là hai thứ khác nhau

Một thư viện có thể có nhiều danh tính:

- **Tên tệp artifact:** ví dụ `codec-1.0.jar`, `codec-1.0-sources.jar` hoặc `codec-1.0-linux.jar`.
- **Tọa độ artifact:** group, artifact và version do Maven/Gradle repository sử dụng.
- **Tên package Java:** ví dụ `com.example.codec`.
- **Tên mô-đun JPMS:** tên được dùng trong `requires`, ví dụ `com.example.codec`.

Những tên này có liên quan về quy ước nhưng không tự động giống nhau. Package `com.example.codec` không buộc module name phải là `com.example.codec`; tọa độ Maven cũng không tự quyết định module name. Với automatic module, tên mặc định được suy ra từ tên JAR theo quy tắc của JDK.

Ví dụ, một thư viện được phát hành dưới tên `codec-utils-1.0.jar` có thể được nhận diện là `codec.utils`. Nếu pipeline đổi artifact thành `codec-core-1.0.jar`, tên suy ra có thể trở thành `codec.core`, dù package và mã nguồn không đổi. Consumer khai báo `requires codec.utils` sẽ không tìm thấy mô-đun cũ khi chỉ có artifact mới.

## 2. Vì sao tên suy ra dễ gây lỗi tương thích?

Tên suy ra phụ thuộc vào quy ước đặt tên artifact, trong khi `requires` là một phần của module descriptor của consumer. Một số thay đổi đóng gói có thể làm đổi tên:

- Đổi artifactId hoặc tên file JAR.
- Thêm hoặc bỏ classifier như `core`, `client`, `all` hoặc `platform`.
- Đổi dấu gạch ngang, dấu gạch dưới hay dấu phân cách khác khiến tên sau chuẩn hóa khác đi.
- Đổi quy ước phát hành hoặc cấu trúc tên trong pipeline.

JDK có thể tách phần version khỏi tên JAR và chuẩn hóa dấu phân cách thành dấu chấm. Vì vậy không nên tự đoán module name từ tên file; hãy xác nhận bằng `jar --describe-module`. Tên suy ra còn có thể không hợp lệ nếu một thành phần bắt đầu bằng chữ số hoặc không thỏa quy tắc định danh Java.

Version được hiển thị sau dấu `@`, ví dụ `codec.utils@1.0 automatic`, là metadata version của mô-đun. Consumer vẫn viết `requires codec.utils;`; JPMS không dùng version trong `requires` như một bộ chọn phiên bản dependency. Đặt hai phiên bản của cùng một module name lên một module path không tạo ra cơ chế chọn phiên bản theo version.

## 3. Công bố tên ổn định bằng `Automatic-Module-Name`

Đối với JAR chưa có `module-info.class`, hãy đặt thuộc tính `Automatic-Module-Name` trong main attributes của manifest:

**`MANIFEST.MF`**

```text
Manifest-Version: 1.0
Automatic-Module-Name: com.example.codec

```

Chọn một tên hợp lệ, ổn định theo quy ước reverse-domain. Không đưa version, classifier hoặc phần mở rộng `.jar` vào tên. Tên này sẽ được các named module sử dụng trong `requires` và cần được giữ nhất quán giữa những lần phát hành tương thích.

Khi JAR có thuộc tính này và chưa có module descriptor, JDK sử dụng giá trị manifest làm tên automatic module, kể cả khi tên file thay đổi. Phiên bản vẫn có thể được nhận diện riêng từ filename:

```text
No module descriptor found. Derived automatic module.

com.example.codec@1.0 automatic
requires java.base mandated
contains com.example.codec
```

`Automatic-Module-Name` chỉ ổn định danh tính mô-đun. JAR vẫn là automatic module: nó đọc các mô-đun khác và export các package của chính nó theo quy tắc automatic module. Thuộc tính này không tạo ra danh sách `requires`, `exports`, `opens`, `uses` hoặc `provides` tường minh.

## 4. Ví dụ kiểm chứng: đổi tên artifact nhưng giữ module name

Ví dụ tạo một thư viện chưa có `module-info.java`, khai báo tên mô-đun trong manifest rồi sao chép JAR sang một tên artifact khác. Consumer biên dịch với artifact đầu tiên và chạy với artifact đã đổi tên.

**`library-src/com/example/codec/Codec.java`**

```java
package com.example.codec;

public final class Codec {
    public String encode(String value) {
        return "encoded:" + value;
    }
}
```

Biên dịch thư viện:

```powershell
New-Item -ItemType Directory -Force lib-classes, lib | Out-Null
javac --release 17 -d lib-classes library-src/com/example/codec/Codec.java
```

Đặt tên mô-đun trong manifest và tạo artifact:

```text
Manifest-Version: 1.0
Automatic-Module-Name: com.example.codec

```

```powershell
jar --create --file lib/codec-1.0.jar --manifest MANIFEST.MF -C lib-classes .
Copy-Item -LiteralPath lib/codec-1.0.jar -Destination lib/codec-renamed-1.0.jar
jar --describe-module --file lib/codec-1.0.jar
jar --describe-module --file lib/codec-renamed-1.0.jar
```

Cả hai artifact đều được nhận diện là `com.example.codec@1.0 automatic`, mặc dù tên tệp khác nhau.

**`consumer-src/com.example.consumer/module-info.java`**

```java
module com.example.consumer {
    requires com.example.codec;
}
```

**`consumer-src/com.example.consumer/com/example/consumer/Main.java`**

```java
package com.example.consumer;

import com.example.codec.Codec;

public class Main {
    public static void main(String[] args) {
        System.out.println(new Codec().encode("hello"));
    }
}
```

Biên dịch consumer bằng JAR đầu tiên, sau đó chạy với JAR đã đổi tên:

```powershell
javac --release 17 --module-path lib/codec-1.0.jar --module-source-path consumer-src -d out -m com.example.consumer
java --module-path "lib/codec-renamed-1.0.jar;out" -m com.example.consumer/com.example.consumer.Main
```

STDOUT:

```text
encoded:hello
```

Consumer chỉ phụ thuộc vào tên mô-đun `com.example.codec`. Nó không cần thay `requires` khi artifact được đổi tên từ `codec-1.0.jar` sang `codec-renamed-1.0.jar`.

## 5. Đối chiếu với JAR không có tên ổn định

Nếu bỏ thuộc tính `Automatic-Module-Name`, cùng thư viện có thể được nhận diện theo tên file:

```powershell
jar --create --file lib/codec-utils-1.0.jar -C lib-classes .
Copy-Item -LiteralPath lib/codec-utils-1.0.jar -Destination lib/codec-core-1.0.jar
jar --describe-module --file lib/codec-utils-1.0.jar
jar --describe-module --file lib/codec-core-1.0.jar
```

JDK sẽ suy ra hai tên khác nhau, tương ứng với `codec.utils@1.0 automatic` và `codec.core@1.0 automatic`. Nếu consumer khai báo `requires codec.utils` nhưng runtime chỉ cung cấp `codec-core-1.0.jar`, quá trình resolve thất bại với lỗi mô-đun `codec.utils` không được tìm thấy.

Điều này cho thấy tên suy ra là kết quả của cách đóng gói. Một thay đổi tên file có thể làm thay đổi hợp đồng module mà không có thay đổi nào trong mã nguồn thư viện.

## 6. Đưa thuộc tính vào quy trình build

Không nên chỉ sửa manifest của một file JAR thủ công sau khi build, vì lần build kế tiếp có thể ghi đè thay đổi. Hãy đặt thuộc tính trong cấu hình đóng gói để mọi artifact phát hành đều nhận cùng tên.

Với Gradle Kotlin DSL trong `build.gradle.kts`:

```kotlin
tasks.jar {
    manifest {
        attributes["Automatic-Module-Name"] = "com.example.codec"
    }
}
```

Với Maven, cấu hình `maven-jar-plugin` để ghi thuộc tính vào manifest của JAR:

```xml
<plugin>
    <artifactId>maven-jar-plugin</artifactId>
    <configuration>
        <archive>
            <manifestEntries>
                <Automatic-Module-Name>com.example.codec</Automatic-Module-Name>
            </manifestEntries>
        </archive>
    </configuration>
</plugin>
```

Trong pipeline phát hành, hãy kiểm tra artifact cuối cùng thay vì chỉ tin cấu hình build. Có thể dùng `jar --describe-module --file path/to/library.jar` để xác nhận tên mà JDK thực sự nhận diện.

## 7. Chuyển từ automatic module sang explicit module

`Automatic-Module-Name` là cầu nối hữu ích khi thư viện chưa có module descriptor. Khi thư viện sẵn sàng modular hóa, thêm `module-info.java` và giữ đúng tên đã công bố:

```java
module com.example.codec {
    exports com.example.codec;
}
```

Khi JAR có `module-info.class`, tên trong descriptor xác định tên mô-đun; `Automatic-Module-Name` trong manifest không ghi đè descriptor. Vì vậy tên explicit mới phải khớp tên automatic đã dùng trước đó nếu muốn consumer giữ nguyên dòng `requires com.example.codec;`.

Việc chuyển sang explicit module cũng cần xem lại các package đang bị consumer sử dụng. Automatic module export tất cả package; explicit module chỉ cho truy cập qua những package được export. Hãy công bố API có chủ đích và kiểm thử consumer trước khi phát hành để tránh làm lộ hoặc vô tình đóng một package mà người dùng đang phụ thuộc.

## 8. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `module not found` sau khi đổi tên JAR | Consumer yêu cầu tên suy ra cũ, trong khi JAR mới có tên mô-đun khác. | Thêm `Automatic-Module-Name` ổn định và phát hành lại; kiểm tra consumer trên module path. |
| `Invalid module name` | Tên suy ra từ filename không tạo thành các thành phần định danh Java hợp lệ. | Đặt tên artifact phù hợp hoặc khai báo `Automatic-Module-Name` hợp lệ. |
| Các artifact khác nhau có cùng module name | Quy tắc chuẩn hóa filename tạo tên trùng nhau. | Chọn module name duy nhất, rõ ràng và ổn định; kiểm tra toàn bộ module path. |
| `Automatic-Module-Name` không có tác dụng | JAR thực tế có `module-info.class`, manifest không nằm trong artifact cuối hoặc consumer đang chạy trên classpath. | Kiểm tra manifest và descriptor của JAR bằng `jar --describe-module`; xác nhận JAR nằm trên module path. |
| Chuyển sang explicit module làm consumer lỗi truy cập | Descriptor mới không export package mà consumer từng truy cập qua automatic module. | Xác định API công khai, export package cần thiết và kiểm thử tương thích. |

Không dùng tên package, Maven artifactId hoặc tên JAR làm module name theo giả định. Những giá trị này có thể tình cờ giống nhau trong một bản build nhưng không có bảo đảm chúng sẽ luôn giống nhau.

## 9. Checklist trước khi phát hành

1. Chọn module name ổn định, hợp lệ và không chứa version/classifier.
2. Đặt `Automatic-Module-Name` trong main attributes của manifest nếu artifact chưa có `module-info.class`.
3. Xác nhận mọi classifier hoặc artifact variant cần hỗ trợ đều dùng đúng module name dự kiến.
4. Chạy `jar --describe-module` trên JAR đã đóng gói trong pipeline.
5. Biên dịch và chạy một named consumer với `requires` theo module name đã công bố.
6. Khi đổi tên artifact, kiểm thử consumer mà không sửa `requires`.
7. Khi thêm explicit descriptor, giữ nguyên module name và kiểm tra lại các package được export.

Tránh phụ thuộc vào tên suy ra từ tên tệp JAR bằng cách công bố một module name ổn định. `Automatic-Module-Name` giữ cho hợp đồng `requires` độc lập với cách build đặt tên artifact; khi thư viện sẵn sàng, explicit module descriptor tiếp tục duy trì danh tính đó và xác định rõ ranh giới API.