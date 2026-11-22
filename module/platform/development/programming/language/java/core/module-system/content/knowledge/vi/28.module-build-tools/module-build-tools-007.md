# javadoc và module documentation

Trong Java Platform Module System (JPMS), tài liệu của một thư viện không chỉ mô tả class, interface và method. Người sử dụng còn cần biết **module nào chứa API**, package nào được export, module phụ thuộc vào những module nào, service nào được sử dụng hoặc cung cấp và các giới hạn truy cập của module. Công cụ `javadoc` hỗ trợ tạo tài liệu HTML cho cấu trúc module, đặc biệt là trang tổng quan của từng named module.

Bài học này hướng dẫn cách viết **module documentation** trong `module-info.java`, kết hợp với tài liệu package/class, khai báo các dịch vụ bằng `@uses` và `@provides`, chạy `javadoc` cho dự án nhiều module và giải thích mối quan hệ giữa tài liệu sinh ra và các quy tắc JPMS thực sự được JVM thi hành.

## 1. Module documentation giải quyết vấn đề gì?

Một dự án Java trước JPMS thường bắt đầu từ tài liệu package:

```text
com.example.catalog.api
com.example.catalog.internal
com.example.catalog.persistence
```

Từ package hoặc class documentation, người đọc biết công dụng của từng kiểu nhưng chưa chắc biết ranh giới triển khai. Sau khi module hóa, có thêm các câu hỏi:

- Tên module để khai báo trong `requires` là gì?
- Package nào là API được export, package nào là implementation nội bộ?
- API công khai phụ thuộc vào module nền tảng hoặc module khác ra sao?
- Có cần `uses` service để nạp implementation bằng `ServiceLoader` không?
- Module cung cấp service nào qua `provides ... with ...`?
- Có module nào được cấp qualified exports hoặc qualified opens?
- Những module nào có thể sử dụng API ổn định mà không cần truy cập package nội bộ?

Javadoc ở cấp module giúp người phát triển đặt câu trả lời trong một trang tổng quan chung, ngay cạnh tài liệu package và public types. Đây cũng là vị trí thích hợp để mô tả cách tích hợp module, điều kiện chạy, service contracts và các giới hạn tương thích.

**Lưu ý:** Javadoc là tài liệu cho con người. Nó không tạo `requires`, `exports`, `opens` hay service provider. Những quan hệ này vẫn được quyết định bởi `module-info.java` và quá trình resolution/runtime.

## 2. Module-info.java vừa là descriptor vừa là nơi viết tài liệu

Một explicit named module có tệp `module-info.java` tại gốc module source tree. Bên trong có khai báo `module` và các directive của JPMS.

Ví dụ:

```java
module com.example.catalog {
    requires java.logging;
    exports com.example.catalog.api;
}
```

Để viết module documentation, đặt một **Javadoc comment** ngay trước khai báo `module`:

```java
/**
 * Cung cấp API tra cứu sản phẩm cho các thành phần của hệ thống.
 *
 * <p>Module này công khai package
 * {@code com.example.catalog.api}, giữ phần lưu trữ
 * và đồng bộ dữ liệu ở các package nội bộ.
 *
 * <p>Các module tiêu thụ khai báo:
 * {@code requires com.example.catalog;}
 *
 * @since 1.0
 */
module com.example.catalog {
    requires java.logging;
    exports com.example.catalog.api;
}
```

Khi chạy `javadoc` ở chế độ module, phần comment này được đưa vào trang tổng quan của module. Nếu không có comment, Javadoc vẫn có thể sinh trang module dựa trên descriptor, nhưng người đọc sẽ thiếu mô tả chủ đích thiết kế, phạm vi sử dụng và hợp đồng API.

Một số nguyên tắc:

1. Dùng `/** ... */` thay vì comment thường `/* ... */` để Javadoc nhận diện.
2. Đặt comment trước khai báo `module`, không đặt rời ở class bất kỳ.
3. Mô tả module ở mức tổng quan; chi tiết mỗi public class nên nằm trong Javadoc của class đó.
4. Đừng biến module documentation thành bản sao toàn bộ source code.
5. Nội dung tài liệu phải nhất quán với descriptor thực tế.

## 3. Cấu trúc source của một dự án nhiều module

Giả sử có ba module:

```text
project/
└── src/
    ├── com.example.codec.api/
    │   ├── module-info.java
    │   └── com/example/codec/api/
    │       ├── Codec.java
    │       └── package-info.java
    ├── com.example.codec.json/
    │   ├── module-info.java
    │   └── com/example/codec/json/
    │       └── JsonCodec.java
    └── com.example.application/
        ├── module-info.java
        └── com/example/application/
            └── Main.java
```

Trong ví dụ:

- `com.example.codec.api` sở hữu hợp đồng `Codec`.
- `com.example.codec.json` triển khai `Codec`.
- `com.example.application` sử dụng service `Codec`.

Với bố cục `src/<module-name>/...`, công cụ `javac` và `javadoc` có thể sử dụng `--module-source-path src` để nhận diện nhiều module.

### 3.1. Module API

`src/com.example.codec.api/module-info.java`:

```java
/**
 * API cho các bộ mã hóa dữ liệu của ứng dụng.
 *
 * <p>Module này công khai giao diện {@link
 * com.example.codec.api.Codec}. Các implementation có thể
 * nằm trong các module provider độc lập.
 *
 * <p>Ứng dụng có thể khai báo
 * {@code requires com.example.codec.api;} để dùng kiểu Codec.
 *
 * @since 1.0
 */
module com.example.codec.api {
    exports com.example.codec.api;
}
```

Giao diện `Codec`:

```java
package com.example.codec.api;

/**
 * Hợp đồng chuyển đổi dữ liệu thành chuỗi.
 *
 * <p>Implementation phải công bố định dạng qua
 * {@link #format()} và trả về kết quả mã hóa qua
 * {@link #encode(String)}.
 *
 * @since 1.0
 */
public interface Codec {

    /**
     * Tên định dạng mà implementation hỗ trợ.
     *
     * @return tên định dạng, ví dụ {@code json}
     */
    String format();

    /**
     * Mã hóa giá trị đầu vào.
     *
     * @param value nội dung cần mã hóa
     * @return dữ liệu đầu ra ở dạng chuỗi
     */
    String encode(String value);
}
```

Module-level documentation giới thiệu mục đích chung; class/interface documentation mô tả contract cụ thể. Hai cấp tài liệu này bổ sung cho nhau.

## 4. package-info.java: tài liệu ở cấp package

Ngoài `module-info.java`, nên dùng `package-info.java` để giải thích một package được export.

Ví dụ `src/com.example.codec.api/com/example/codec/api/package-info.java`:

```java
/**
 * Các API mã hóa dữ liệu dùng chung.
 *
 * <p>Package này định nghĩa hợp đồng ổn định cho
 * các codec. Ứng dụng không cần phụ thuộc trực tiếp
 * vào package triển khai của từng provider.
 *
 * @since 1.0
 */
package com.example.codec.api;
```

Javadoc có thể dùng comment này để tạo trang tổng quan cho package. Sự phân công hợp lý:

| Cấp tài liệu | Nên mô tả |
|---|---|
| Module `module-info.java` | Mục tiêu module, cách tích hợp, module dependency, service contracts |
| Package `package-info.java` | Vai trò package, những kiểu liên quan và nguyên tắc sử dụng |
| Class/interface | Trách nhiệm, bất biến, quy tắc kế thừa hoặc triển khai |
| Constructor/method/field | Tham số, kết quả, lỗi, hành vi và điều kiện sử dụng |

Không bắt buộc phải có `package-info.java` cho mọi package, nhưng rất hữu ích với package API lớn hoặc có nhiều interface phối hợp.

## 5. Tài liệu service với @uses và @provides

JPMS hỗ trợ service abstraction bằng hai directive:

- `uses service.Interface;` trong module sử dụng service.
- `provides service.Interface with provider.Implementation;` trong module cung cấp service.

Javadoc có các block tag `@uses` và `@provides` để giải thích ý nghĩa của những service này trên trang module.

### 5.1. Module tiêu thụ service

`src/com.example.application/module-info.java`:

```java
/**
 * Ứng dụng lựa chọn bộ mã hóa dữ liệu tại runtime.
 *
 * <p>Ứng dụng phụ thuộc vào API Codec, không phụ thuộc
 * trực tiếp vào từng module implementation.
 *
 * @uses com.example.codec.api.Codec
 *       Dùng để khám phá codec khả dụng bằng ServiceLoader.
 *
 * @since 1.0
 */
module com.example.application {
    requires com.example.codec.api;
    uses com.example.codec.api.Codec;
}
```

Ở đây:

- `requires` cho phép module đọc module API chứa `Codec`.
- `uses` khai báo service dependency cho JPMS.
- `@uses` cung cấp mô tả hiển thị trong tài liệu module.

Nếu chỉ viết `@uses` nhưng không khai báo `uses` tương ứng, nội dung tài liệu không tự tạo service dependency trong module graph.

### 5.2. Module cung cấp service

`src/com.example.codec.json/module-info.java`:

```java
/**
 * Provider mã hóa dữ liệu ở định dạng JSON.
 *
 * <p>Module triển khai hợp đồng Codec và có thể được
 * phát hiện thông qua ServiceLoader sau khi được
 * đưa vào module graph.
 *
 * @provides com.example.codec.api.Codec
 *           Provider mã hóa ở định dạng JSON.
 *
 * @since 1.0
 */
module com.example.codec.json {
    requires com.example.codec.api;

    provides com.example.codec.api.Codec
        with com.example.codec.json.JsonCodec;
}
```

Implementation:

```java
package com.example.codec.json;

import com.example.codec.api.Codec;

/**
 * Implementation minh họa của {@link Codec}.
 *
 * <p>Ví dụ rút gọn để tập trung vào JPMS;
 * không phải implementation JSON hoàn chỉnh.
 */
public final class JsonCodec implements Codec {

    public JsonCodec() {}

    @Override
    public String format() {
        return "json";
    }

    @Override
    public String encode(String value) {
        return "\""+value.replace("\"","\\\"")+"\"";
    }
}
```

Điểm cốt lõi: `@provides` mô tả service được module cung cấp; directive `provides` mới là metadata mà module system sử dụng khi làm service binding.

Provider package không bắt buộc phải được export chỉ để `ServiceLoader` nhận provider đã khai báo trong module descriptor. Nếu người dùng chỉ cần service interface, họ nên tương tác qua `Codec` thay vì import trực tiếp lớp triển khai.

## 6. Javadoc có thể hiển thị gì từ module descriptor?

Khi `javadoc` xử lý một named module, trang tài liệu có thể thể hiện những thông tin từ descriptor, ví dụ:

- Tên module.
- Mô tả module từ Javadoc comment.
- Các module được yêu cầu bằng `requires`.
- Các package được export.
- Những service được khai báo trong `uses` và `provides`.
- Những thông tin liên quan đến các dependency bắc cầu hoặc package được mở, tùy lựa chọn hiển thị.

Ví dụ descriptor:

```java
module com.example.catalog {
    requires transitive com.example.money;
    requires java.logging;
    exports com.example.catalog.api;
    exports com.example.catalog.integration
        to com.example.reporting;
    opens com.example.catalog.model
        to com.example.json;
}
```

Tài liệu cần giải thích vì sao có từng quyết định quan trọng:

- `requires transitive` thường thích hợp khi public API của module để lộ kiểu thuộc dependency khác.
- `exports` công khai package cho module khác có readability phù hợp.
- Qualified exports chỉ công khai package cho module đích được chỉ định.
- `opens` phục vụ deep reflection, khác với API public access thông thường.

Không nên cố sao chép toàn bộ bảng dependency vào comment nếu descriptor đã thể hiện chính xác; phần mô tả nên giải thích *mục đích và cách dùng*.

## 7. Tạo tài liệu bằng javadoc --module-source-path

Với cấu trúc source nhiều module đã nêu, lệnh cơ bản là:

```shell
javadoc -d docs --module-source-path src \
        --module com.example.codec.api,com.example.codec.json,com.example.application
```

Giải thích:

- `-d docs`: thư mục đầu ra HTML.
- `--module-source-path src`: nơi tìm source của các module theo cấu trúc module source path.
- `--module`: danh sách module sẽ được đưa vào lần tạo tài liệu.

Trên Windows PowerShell, có thể viết thành một dòng để tránh khác biệt escape xuống dòng giữa các shell:

```powershell
javadoc -d docs --module-source-path src --module com.example.codec.api,com.example.codec.json,com.example.application
```

Lệnh tạo tài liệu của các module được chọn cùng những package/type thuộc phạm vi hiển thị. Sau khi hoàn tất, mở trang `docs/index.html` bằng trình duyệt; cấu trúc đầu ra có thể chứa trang module-summary và các trang package/class tương ứng.

Nếu project có thêm dependency modular từ JAR không nằm trong source tree, cung cấp module path:

```shell
javadoc -d docs \
        --module-source-path src \
        --module-path libs \
        --module com.example.application
```

`--module-path` trong ngữ cảnh này giúp công cụ tìm dependency của module được tài liệu hóa. Nó không có nghĩa Javadoc sẽ tự động sinh đầy đủ tài liệu cho mọi JAR dependency không có source.

## 8. Chỉ tài liệu hóa module cần phát hành

Một repository có thể chứa hàng chục module, nhưng không phải module nào cũng là API công khai.

Giả sử có:

```text
com.example.catalog.api
com.example.catalog.impl
com.example.catalog.integration.tests
com.example.devtools
```

Khi phát hành tài liệu API, có thể chỉ chọn những module người dùng cần tham chiếu:

```shell
javadoc -d docs/public \
        --module-source-path src \
        --module com.example.catalog.api
```

Nếu tài liệu phục vụ nhóm phát triển nội bộ, có thể thêm những module khác:

```shell
javadoc -d docs/internal \
        --module-source-path src \
        --module com.example.catalog.api,com.example.catalog.impl
```

Việc tách tài liệu public và internal giúp bảo vệ ranh giới contract. Tuy nhiên, lựa chọn module nào được tài liệu hóa không làm thay đổi module graph; đó chỉ là quyết định về phạm vi xuất bản tài liệu.

## 9. Tài liệu package được export và package nội bộ

Theo mô hình JPMS, package được `exports` là bề mặt API thông thường của module. Package implementation không export thường không nên được mô tả như API hỗ trợ cho người dùng bên ngoài.

Javadoc có các tùy chọn kiểm soát phạm vi hiển thị, chẳng hạn:

```shell
javadoc --show-module-contents api \
        --module-source-path src \
        --module com.example.catalog.api \
        -d docs/api
```

Với tài liệu nội bộ, có thể chọn phạm vi rộng hơn:

```shell
javadoc --show-module-contents all \
        --module-source-path src \
        --module com.example.catalog.api \
        -d docs/all
```

Ngoài ra, tùy chọn `--show-packages` có thể được dùng để kiểm soát loại package được đưa vào tài liệu theo giá trị hỗ trợ bởi phiên bản JDK, chẳng hạn `exported` hoặc `all`.

Các tùy chọn này quyết định **nội dung tài liệu HTML được tạo**. Chúng không export package nội bộ tại runtime. Một package xuất hiện trong tài liệu nội bộ vẫn có thể bị JPMS chặn khi module khác cố import.

Khi xây dựng website API công khai, ưu tiên tài liệu đúng các module và package thuộc contract ổn định.

## 10. Sử dụng liên kết trong Javadoc

Một comment tốt không nên lặp lại toàn bộ chữ ký API. Thay vào đó, dùng inline tag để dẫn người đọc tới type và member liên quan.

Ví dụ:

```java
/**
 * API điều phối đơn hàng.
 *
 * <p>Tra cứu chi tiết tại
 * {@link com.example.catalog.api.CatalogService}.
 * Các ứng dụng có thể sử dụng interface này cùng
 * {@link java.util.Optional} để biểu diễn kết quả.
 */
module com.example.orders {
    requires com.example.catalog;
    exports com.example.orders.api;
}
```

Các tag phổ biến:

- `{@link Type}`: tạo link tới kiểu hoặc thành viên.
- `{@linkplain Type nhãn hiển thị}`: tạo link với nhãn văn bản thường.
- `{@code ...}`: hiển thị một đoạn mã inline mà không phân tích markup HTML bên trong.
- `@see`: liệt kê tài liệu liên quan.
- `@since`: ghi phiên bản mà API/module được giới thiệu.
- `@deprecated`: ghi chú phần không còn được khuyến nghị sử dụng; áp dụng theo ngữ cảnh tài liệu phù hợp.

Nếu muốn tài liệu liên kết tới Java SE API, có thể dùng:

```shell
javadoc -d docs \
        --module-source-path src \
        --module com.example.catalog \
        -link https://docs.oracle.com/en/java/javase/21/docs/api/
```

Đường dẫn Java 21 trên chỉ minh họa; khi phát hành hãy chọn tài liệu đúng phiên bản Java mục tiêu. Việc liên kết tới site ngoài có thể yêu cầu kết nối mạng ở bước sinh tài liệu.

## 11. requires và requires transitive trong tài liệu API

Khi viết module documentation, nên nêu rõ dependency nào là một phần contract công khai.

Ví dụ module catalog export API trả về một kiểu từ module money:

```java
module com.example.catalog {
    requires transitive com.example.money;
    exports com.example.catalog.api;
}
```

Nếu method public của catalog có kiểu trả về hoặc tham số thuộc money module, consumer đọc catalog có thể cần readability tới money. `requires transitive` công bố quan hệ này tới các module đọc catalog.

Ở tài liệu module, nên giải thích:

- Người dùng chỉ cần khai báo `requires com.example.catalog;` trong trường hợp nào?
- Những kiểu thuộc module khác xuất hiện trong public API ở đâu?
- Có những dependency chỉ dùng nội bộ, không được bảo đảm như contract không?
- Những tính năng nào phụ thuộc optional provider hoặc môi trường runtime?

Tài liệu không thay thế việc kiểm tra descriptor. Nếu comment ghi rằng money là dependency transitive nhưng source chỉ có `requires com.example.money;`, tài liệu và contract thực tế sẽ không khớp nhau.

## 12. Mối quan hệ giữa opens và tài liệu framework

Một số thư viện được thiết kế để dùng với framework reflection như ORM, serialization hoặc dependency injection.

Ví dụ:

```java
module com.example.domain {
    exports com.example.domain.api;
    opens com.example.domain.model
        to com.example.orm;
}
```

Module documentation có thể mô tả rằng:

- Package `com.example.domain.api` là API sử dụng thông thường.
- Package `com.example.domain.model` chỉ được mở cho reflection của `com.example.orm`.
- Consumer không được giả định package model là public API chỉ vì framework có thể truy cập sâu.

Directive `opens` không giống `exports`. `exports` cho phép truy cập public types theo quy tắc Java; `opens` phục vụ deep reflection. Việc xuất hiện trong Javadoc không làm hai directive này trở nên tương đương.

Nếu framework phụ thuộc runtime flags như `--add-opens`, nên ghi chúng trong hướng dẫn triển khai và có lý do rõ ràng, không chỉ đặt trong comment của một class bất kỳ.

## 13. Tài liệu cho module sử dụng ServiceLoader

Khi module hỗ trợ plugin qua service interface, người dùng cần biết cách cung cấp hoặc tiêu thụ provider.

Ví dụ mô tả:

```java
/**
 * Module ứng dụng xử lý đầu ra qua hệ thống codec.
 *
 * <p>Plugin codec cần công bố service provider theo
 * {@code provides ... with ...} trong module descriptor.
 *
 * @uses com.example.codec.api.Codec
 *       Tìm codec được cài đặt khi chương trình chạy.
 */
module com.example.application {
    requires com.example.codec.api;
    uses com.example.codec.api.Codec;
}
```

Và trong provider module:

```java
/**
 * Provider codec JSON.
 *
 * @provides com.example.codec.api.Codec
 *           Cung cấp định dạng JSON.
 */
module com.example.codec.json {
    requires com.example.codec.api;
    provides com.example.codec.api.Codec
        with com.example.codec.json.JsonCodec;
}
```

Hãy tách biệt:

1. **Service declaration:** `uses` và `provides` trong descriptor.
2. **Service binding:** các API resolution như `Configuration.resolveAndBind` có thể bổ sung provider module vào graph.
3. **Service discovery:** `ServiceLoader` tìm provider trong runtime context phù hợp.
4. **Service documentation:** `@uses`, `@provides` giải thích ý nghĩa của hợp đồng trên trang tài liệu.

Một documentation website có thể liệt kê service provider, nhưng không thay thế việc đưa module provider thực tế vào runtime graph.

## 14. javadoc với Maven và Gradle

Trong dự án lớn, nên tích hợp sinh tài liệu vào build thay vì chạy lệnh thủ công cho mỗi lần phát hành.

### 14.1. Maven

Maven Javadoc Plugin có thể sinh Javadoc cho module hoặc reactor project, tùy cách tổ chức các Maven modules và phiên bản plugin.

Một cấu hình minh họa:

```xml
<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-javadoc-plugin</artifactId>
      <version>3.11.2</version>
    </plugin>
  </plugins>
</build>
```

Sau đó chạy goal phù hợp như `mvn javadoc:javadoc` hoặc `mvn javadoc:aggregate` đối với dự án nhiều module khi cấu hình hỗ trợ. Số phiên bản trên chỉ minh họa; sử dụng phiên bản plugin phù hợp với build và toolchain thật.

Nếu build chạy trên JPMS, cần kiểm tra plugin có truyền đúng module path, module source path và scope dependency hay không. Không phải mọi dự án nhiều Maven module đều tương ứng một-một với JPMS named module.

### 14.2. Gradle

Gradle có task `javadoc` trong Java ecosystem:

```shell
./gradlew javadoc
```

Với dự án multi-project, có thể tạo task tổng hợp tùy nhu cầu xuất bản. Cần xác minh phiên bản Gradle và cấu hình modularity để các Javadoc task nhận đúng source/module path.

Đừng kết luận rằng tài liệu sinh ra ở chế độ JPMS chỉ vì source tree có `module-info.java`. Hãy kiểm tra output xem có trang module summary và thông tin `requires`, `exports`, service như dự kiến không.

## 15. Kiểm tra cảnh báo của javadoc

Javadoc có thể báo lỗi hoặc cảnh báo khi:

- Một tag `{@link ...}` trỏ tới kiểu hoặc thành viên không tồn tại.
- `@param` không khớp tham số method.
- Tài liệu dùng markup HTML không hợp lệ.
- Dependency/module cần để phân giải kiểu không nằm trên path.
- Một module được chỉ định nhưng thiếu source hoặc module descriptor.
- Các tag mô tả chưa đầy đủ hoặc sai cú pháp.

Có thể bật các mức kiểm tra tài liệu qua `-Xdoclint` theo khả năng của phiên bản JDK:

```shell
javadoc -Xdoclint:all \
        --module-source-path src \
        --module com.example.codec.api \
        -d docs
```

Những cảnh báo này giúp phát hiện lỗi markup hoặc thông tin Javadoc chưa hợp lệ. Chúng không chứng minh rằng thiết kế JPMS hoặc module graph runtime là đúng. Nên kết hợp việc sinh tài liệu với build và test thông thường.

## 16. Những nhầm lẫn thường gặp

**Đặt tài liệu module trong README nhưng bỏ trống module-info.java.**

README là tài liệu bổ sung tốt, nhưng `javadoc` không tự lấy nội dung README để tạo module summary. Nếu cần trang module có phần giới thiệu riêng, dùng Javadoc comment trước khai báo module.

**Nhầm @uses với uses.**

`@uses` chỉ mô tả service trong tài liệu. `uses` mới là directive trong module descriptor.

**Nhầm @provides với provides ... with ....**

`@provides` cung cấp mô tả hiển thị trong HTML; `provides` mới là metadata service provider được JPMS nhận diện.

**Nghĩ package được mô tả trong tài liệu là package được export.**

Quyền truy cập được quyết định bởi `exports` và readability. Javadoc có thể tạo tài liệu nội bộ cho package không export mà không thay đổi quyền truy cập.

**Nghĩ mọi dependency có trên module path sẽ tự được tài liệu hóa.**

Module path giúp công cụ phân giải dependency. Muốn xuất bản tài liệu cho một module, phải cung cấp source hoặc cấu hình tài liệu phù hợp và chọn module cần tài liệu hóa.

**Viết tài liệu theo tên JAR thay vì tên module.**

JPMS dùng module name được khai báo trong descriptor; tên artifact Maven hoặc file JAR có thể khác. Hãy ghi đúng module name để người dùng viết `requires` chính xác.

**Dùng link tới API của JDK phiên bản khác mà không ghi rõ.**

API có thể thay đổi theo phiên bản Java. Hãy chọn link và mức tương thích phù hợp với target JDK.

**Đưa package implementation vào tài liệu API công khai.**

Điều này khiến người dùng hiểu nhầm implementation là contract ổn định. Nên tách tài liệu public và internal theo chủ đích.

## 17. Quy trình viết và xuất bản module documentation

Một quy trình dễ áp dụng:

1. **Xác định tên module:** kiểm tra `module-info.java`.
2. **Chốt package công khai:** những package nào cần `exports` và vì sao.
3. **Viết phần giới thiệu module:** mục đích, phạm vi, contract và giới hạn sử dụng.
4. **Mô tả dependency quan trọng:** đặc biệt `requires transitive` nếu public API dùng kiểu của module khác.
5. **Viết @uses/@provides khi có service:** đồng bộ với các directive tương ứng.
6. **Viết package-info.java:** mô tả API theo từng package được export.
7. **Bổ sung Javadoc cho type/member:** `@param`, `@return`, `@throws`, `{@link}`, `@since`.
8. **Sinh HTML:** dùng `javadoc --module-source-path ... --module ...`.
9. **Kiểm tra output:** trang module summary, package summary và link tới kiểu cần thiết.
10. **Xuất bản theo phạm vi:** tài liệu API công khai khác tài liệu implementation nội bộ khi cần.
11. **Gắn với release:** sinh lại tài liệu từ source của đúng commit/tag và JDK target.
12. **Duy trì đồng bộ:** khi thay `exports`, `uses`, `provides` hoặc public API, cập nhật module documentation trong cùng thay đổi.

## 18. Checklist module documentation

- [ ] `module-info.java` có Javadoc comment trước khai báo module.
- [ ] Comment mô tả đúng trách nhiệm và phạm vi của module.
- [ ] Module name được ghi chính xác trong hướng dẫn tích hợp.
- [ ] Các package API có `exports` phù hợp; package nội bộ không bị gọi nhầm là public API.
- [ ] `requires transitive` được giải thích khi dependency xuất hiện trong public API.
- [ ] Các `uses` và `provides` quan trọng có mô tả qua `@uses`/`@provides`.
- [ ] Các package công khai có `package-info.java` khi cần.
- [ ] Javadoc của public type và method có contract rõ ràng.
- [ ] Các `{@link}` tới type/member khác được phân giải thành công.
- [ ] Lệnh Javadoc dùng đúng `--module-source-path`, `--module` và module path dependency.
- [ ] Trang module summary hiển thị đúng nội dung và service-related sections.
- [ ] Tài liệu được tạo từ phiên bản source và toolchain đúng với bản phát hành.

## Kết luận

`javadoc` giúp biến một module JPMS từ tập class có descriptor thành một **thành phần có hợp đồng sử dụng được mô tả rõ ràng**. Javadoc comment trong `module-info.java` cung cấp mô tả cấp module; `package-info.java` giải thích vai trò các package; tài liệu class và member mô tả API cụ thể. Các tag `@uses` và `@provides` bổ sung phần giải thích cho service dependencies.

Với dự án nhiều module, dùng `javadoc --module-source-path ... --module ...` để sinh tài liệu HTML có trang tổng quan module. Các tùy chọn phạm vi hiển thị giúp tách API công khai khỏi implementation nội bộ; việc lựa chọn nội dung xuất bản không làm thay đổi `requires`, `exports`, `opens` hay quá trình module resolution.

Tài liệu module tốt phải nhất quán với descriptor thực tế, hướng dẫn đúng module name, mô tả đầy đủ service contract và được sinh lại theo mỗi bản phát hành. Nhờ đó, người sử dụng hiểu không chỉ cách gọi một class, mà còn cách tích hợp module vào module graph một cách có chủ đích.
