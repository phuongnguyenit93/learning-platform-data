# PropertyValueConverter và ngữ cảnh chuyển đổi theo phiên bản

## 1. Khi cùng một kiểu Java cần nhiều cách lưu khác nhau

Trong chương **Chuyển đổi dữ liệu** của **SPRING_DATA_COMMONS**, chuyển đổi theo thuộc tính giải quyết một nhu cầu khác với converter theo cặp kiểu: cùng là `String`, nhưng mỗi thuộc tính có thể có hợp đồng lưu trữ riêng.

Ví dụ, một đơn hàng có hai thuộc tính:

```java
class Order {
    String deliveryNote;
    String customerComment;
}
```

Ứng dụng muốn `deliveryNote` được lưu bằng định dạng có phiên bản để thay đổi cách mã hóa về sau, còn `customerComment` vẫn được lưu như chuỗi thông thường. Nếu đăng ký một converter `String -> String` trên phạm vi quá rộng, cả hai thuộc tính có thể bị ảnh hưởng ngoài ý định.

`PropertyValueConverter` cung cấp abstraction cho việc chuyển đổi giá trị gắn với một thuộc tính. Converter nhận thêm context, nhờ đó có thể sử dụng metadata hoặc những khả năng mà module store cung cấp cho lần chuyển đổi đó.

Bài học tập trung vào bốn câu hỏi:

- Converter theo thuộc tính khác converter theo kiểu ở điểm nào?
- Context cung cấp điều gì, và giới hạn của nó nằm ở đâu?
- Phải kiểm tra gì khi API và module Spring Data có phiên bản khác nhau?
- Làm thế nào đọc dữ liệu cũ, ghi dữ liệu mới mà không nhầm với cơ chế `@Version`?

## 2. Phân biệt ba nghĩa của “phiên bản”

Trước khi thiết kế converter, cần tách rõ ba khái niệm độc lập.

| Loại phiên bản | Ví dụ | Tác động đến conversion |
| --- | --- | --- |
| Phiên bản thư viện | Phiên bản Spring Data Commons và module store trong dependency graph | Quyết định API, điểm đăng ký và khả năng tích hợp có sẵn |
| Phiên bản định dạng dữ liệu | Chuỗi có tiền tố `v1:` hoặc `v2:` | Quyết định cách giải mã giá trị đã lưu |
| Phiên bản phục vụ optimistic locking | Thuộc tính dùng annotation `@Version` trong module hỗ trợ | Phát hiện xung đột cập nhật theo cơ chế của module |

Context của `PropertyValueConverter` không tự đồng nhất ba loại phiên bản này. Đổi phiên bản thư viện không tự nâng phiên bản dữ liệu. Có một field `@Version` cũng không tự cung cấp giao thức giải mã cho các field khác.

Một kế hoạch conversion đúng cần xác định riêng: API nào đang chạy, định dạng nào đang tồn tại trong store, và cơ chế kiểm soát cập nhật nào được sử dụng.

## 3. Hợp đồng của `PropertyValueConverter`

Abstraction nằm trong package:

```java
import org.springframework.data.convert.PropertyValueConverter;
```

Có thể đọc ý nghĩa ba tham số generic như sau:

```text
PropertyValueConverter<D, S, C>

D: kiểu giá trị trong domain
S: kiểu biểu diễn mà converter trao đổi với tầng mapping của store
C: kiểu context hợp lệ cho converter
```

Hai thao tác cốt lõi có hướng ngược nhau:

```text
read  : S -> D
write : D -> S
```

Ví dụ:

| Kiểu domain D | Kiểu lưu trữ S | Ý định |
| --- | --- | --- |
| `String` | `String` | Một thuộc tính dùng định dạng chuỗi riêng |
| Value object | `String` | Lưu một giá trị nghiệp vụ thành chuỗi |
| Kiểu domain | Kiểu giá trị đặc thù của store | Tận dụng biểu diễn mà module/driver hỗ trợ |

Kiểu `S` không nhất thiết là byte cuối cùng nằm trên đĩa. Sau converter, module store hoặc driver vẫn có thể thực hiện bước binding, serialization hay xử lý biểu diễn riêng.

### 3.1. Cùng cặp kiểu nhưng khác phạm vi

Converter theo kiểu thường được tìm dựa vào kiểu nguồn, kiểu đích và hướng chuyển đổi trong cấu hình liên quan. Converter theo thuộc tính được chọn cho một persistent property cụ thể theo cơ chế mà module hỗ trợ.

Điểm khác biệt thể hiện rõ khi cả `D` và `S` đều là `String`: phương thức `read` và `write` vẫn có hai vai trò riêng, còn việc thuộc tính nào sử dụng converter là một quyết định cấu hình khác.

Không cần biến mọi `String` trong ứng dụng thành một kiểu khác chỉ để một field có biểu diễn đặc biệt.

### 3.2. Converter xử lý giá trị, không thay thế repository

`PropertyValueConverter` không phải hook mặc định cho toàn bộ nghiệp vụ lưu aggregate. Nó không tự phân trang, không tự tạo index, không tự mở transaction và không thay đổi hợp đồng CRUD của repository.

Các abstraction dùng chung của Spring Data giúp tổ chức repository và metadata, nhưng khả năng chuyển đổi thực tế vẫn phụ thuộc module store đang thực hiện mapping.

## 4. `ValueConversionContext` là gì?

Context dùng chung được biểu diễn qua `ValueConversionContext`:

```java
import org.springframework.data.convert.ValueConversionContext;
```

Một converter không cần API riêng của store có thể dùng dạng:

```java
PropertyValueConverter<String, String, ValueConversionContext<?>>
```

Context cho phép converter nhận thông tin gắn với lần chuyển đổi. Metadata thuộc tính là điểm quan trọng: converter có thể biết đang xử lý property nào thay vì suy luận từ tên lớp hoặc từ một biến toàn cục.

Ví dụ truy cập tên thuộc tính:

```java
String propertyName = context.getProperty().getName();
```

Giá trị này hữu ích khi tạo thông báo lỗi có vị trí rõ ràng. Nếu nhiều thuộc tính cùng dùng một converter, lỗi có thể chỉ ra đúng thuộc tính gây vấn đề.

### 4.1. Những khả năng cần kiểm tra theo API và module

Tùy API và implementation, context có thể cung cấp cơ chế ủy quyền đọc/ghi một giá trị khác hoặc truy cập thêm dữ liệu liên quan. Không nên suy ra rằng mọi context đều hỗ trợ đầy đủ cùng một tập thao tác.

| Nhu cầu | Cách tiếp cận |
| --- | --- |
| Đọc metadata property | Sử dụng hợp đồng metadata của context |
| Ủy quyền một conversion khác | Kiểm tra phương thức và implementation mà phiên bản đang dùng hỗ trợ |
| Đọc giá trị thuộc tính khác | Xác định có được hỗ trợ không, giá trị thuộc tầng nào và khả dụng ở hướng nào |
| Lấy tenant, người dùng hoặc request hiện tại | Thiết kế nguồn ngữ cảnh rõ ràng; không mặc định context conversion có sẵn thông tin đó |
| Thay đổi aggregate hoặc transaction | Dùng cơ chế phù hợp ở tầng ứng dụng/mapping; không coi đây là trách nhiệm mặc định của context |

Một phương thức tồn tại trên interface không đủ để chứng minh implementation của module thực hiện đầy đủ thao tác đó. Cần kiểm tra cả hợp đồng và khả năng thực tế.

### 4.2. Context không phải toàn bộ object graph

Nếu định dạng của `deliveryNote` phụ thuộc vào `schemaVersion` ở field bên cạnh, phải trả lời được các câu hỏi:

- Context có đọc được field đó trên đường ghi và đường đọc không?
- Giá trị nhận được là giá trị domain hay biểu diễn đang nằm trong store?
- Property chưa có hoặc bị bỏ khỏi projection thì xử lý thế nào?
- Có phụ thuộc vào thứ tự materialize các thuộc tính không?
- Native query hoặc aggregation có đi qua cùng context không?

Không nên giả định converter được chạy sau khi toàn bộ entity đã hoàn chỉnh. Một lựa chọn đơn giản hơn cho một số bài toán là đặt dấu hiệu phiên bản ngay trong chính giá trị cần giải mã.

### 4.3. Tránh ủy quyền trở lại đúng đường chuyển đổi đang chạy

Nếu context cho phép delegate, không gọi lại cùng property và cùng phép chuyển đổi một cách vô điều kiện. Điều đó có thể quay lại converter hiện tại và gây đệ quy.

Chỉ delegate khi đã hiểu cặp kiểu, đường xử lý và điều kiện dừng. Nếu logic chỉ cần một phép biến đổi chuỗi thuần túy, thực hiện trực tiếp thường dễ kiểm chứng hơn.

## 5. Kiểm tra tương thích theo phiên bản trước khi cấu hình

Việc thấy `PropertyValueConverter` trong dependency không chứng minh module store đang sử dụng tính năng đó ở mọi đường đọc/ghi.

Cần kiểm tra các lớp tương thích sau:

| Lớp cần kiểm tra | Câu hỏi cụ thể |
| --- | --- |
| Dependency graph | Commons và module store có thuộc tập phiên bản tương thích không? |
| API Commons | Generic, annotation, factory và cơ chế null nào có trong phiên bản đang dùng? |
| Tích hợp store | Mapper của module có hỗ trợ property conversion không? |
| Điểm đăng ký | Module dùng annotation, registry, factory hay cấu hình riêng nào? |
| Context thực tế | Loại context nào được truyền vào, thao tác nào được hỗ trợ? |
| Đường truy cập dữ liệu | Save, load, query, projection, update và aggregation có hành vi gì? |

Trong một ứng dụng được quản lý dependency bằng Spring Boot hoặc BOM, cần đánh giá tập phiên bản do cơ chế quản lý đó cung cấp. Chỉ nâng riêng Commons để có một API mới có thể dẫn đến lệch API với module còn lại.

Bài này không gán một mốc phiên bản số cho tất cả store. Khi triển khai, hãy đối chiếu đúng tài liệu/API của tập dependency mà project sử dụng, rồi xác nhận bằng kiểm tra tích hợp trên module đó.

### Phân biệt Commons với cơ chế của JPA provider

Không nên mặc định một annotation conversion của Commons điều khiển việc ghi cột của Spring Data JPA. JPA provider có cơ chế mapping và conversion riêng, chẳng hạn attribute converter của JPA khi phù hợp.

Cùng có repository abstraction không có nghĩa các module chia sẻ toàn bộ pipeline persistence. Một ví dụ hoạt động với module tài liệu không tự trở thành công thức cấu hình cho JPA, JDBC hay Redis.

## 6. Thiết kế định dạng dữ liệu có phiên bản

Giả sử `deliveryNote` trong domain vẫn là một chuỗi. Ứng dụng có hai định dạng lưu trữ:

| Định dạng | Dữ liệu được lưu | Quy tắc đọc |
| --- | --- | --- |
| `v1` | `v1:` cộng nội dung nguyên văn | Bỏ tiền tố để nhận chuỗi domain |
| `v2` | `v2:` cộng nội dung UTF-8 được Base64 URL encode | Decode phần payload thành chuỗi domain |

Chính sách chuyển tiếp:

- Đọc được cả `v1` và `v2`.
- Mọi lần ghi mới đều tạo `v2`.
- Tiền tố không được hỗ trợ phải gây lỗi rõ ràng.
- Payload `v2` sai định dạng phải bị từ chối.
- Không tự coi chuỗi không có tiền tố là một định dạng đã biết.

Base64 trong ví dụ là phép biểu diễn dữ liệu để minh họa chuyển đổi, không phải mã hóa bảo mật.

### 6.1. Vì sao đặt phiên bản trong chính giá trị?

Converter chỉ cần giá trị đang được đọc để xác định cách giải mã. Nó không phụ thuộc việc context có thể đọc một field `schemaVersion` khác hay không.

Đây không phải lựa chọn bắt buộc cho mọi hệ thống. Với cấu trúc tài liệu hoặc schema có metadata riêng, có thể cần một thiết kế khác. Điều quan trọng là nguồn xác định phiên bản phải rõ ràng và khả dụng ở đúng đường đọc.

### 6.2. Ví dụ biểu diễn cụ thể

Với domain value `hello`:

```text
Dữ liệu cũ: v1:hello
Dữ liệu mới: v2:aGVsbG8
Domain sau khi đọc: hello
```

Một chuỗi domain bắt đầu bằng `v1:` hoặc `v2:` vẫn chỉ là nội dung của người dùng ở hướng ghi. Converter luôn encode toàn bộ nội dung và thêm tiền tố lưu trữ ở ngoài. Vì vậy nó không nhầm nội dung domain với metadata định dạng khi ghi.

## 7. Triển khai converter không phụ thuộc context riêng của store

Ví dụ sau dùng `PropertyValueConverter`, metadata từ context và các API JDK. Nó minh họa logic chuyển đổi; việc đăng ký và khả năng gọi converter còn phải được module store hỗ trợ.

```java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.Base64;

import org.springframework.data.convert.PropertyValueConverter;
import org.springframework.data.convert.ValueConversionContext;

public final class VersionedNoteConverter
        implements PropertyValueConverter<
                String, String, ValueConversionContext<?>> {

    private static final String V1 = "v1:";
    private static final String V2 = "v2:";

    @Override
    public String read(String value, ValueConversionContext<?> context) {
        if (value.startsWith(V1)) {
            return value.substring(V1.length());
        }

        if (value.startsWith(V2)) {
            return decodeV2(value.substring(V2.length()), context);
        }

        throw invalid(context, "unsupported or missing format version", null);
    }

    @Override
    public String write(String value, ValueConversionContext<?> context) {
        String payload = Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(value.getBytes(StandardCharsets.UTF_8));

        return V2 + payload;
    }

    private String decodeV2(
            String payload,
            ValueConversionContext<?> context) {

        try {
            byte[] bytes = Base64.getUrlDecoder().decode(payload);

            return StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(bytes))
                    .toString();
        } catch (IllegalArgumentException | CharacterCodingException ex) {
            throw invalid(context, "invalid v2 payload", ex);
        }
    }

    private IllegalArgumentException invalid(
            ValueConversionContext<?> context,
            String reason,
            Throwable cause) {

        String propertyName = context.getProperty().getName();

        return new IllegalArgumentException(
                "Cannot convert property '" + propertyName + "': " + reason,
                cause
        );
    }
}
```

### 7.1. Những quyết định trong đoạn code

**Hướng đọc chấp nhận nhiều phiên bản.** Converter chọn thuật toán theo tiền tố của biểu diễn đã lưu. Nó không chọn theo phiên bản hiện tại của thư viện hoặc theo `@Version`.

**Hướng ghi chỉ tạo một định dạng chuẩn.** Mỗi lần ghi đều sinh `v2`, giúp dữ liệu mới nhất quán. Điều đó không tự backfill các bản ghi chưa được ghi lại.

**UTF-8 được xác định rõ.** Converter không dùng charset mặc định của hệ điều hành. Decoder được cấu hình để từ chối byte UTF-8 không hợp lệ thay vì âm thầm thay thế ký tự.

**Context phục vụ thông tin thuộc tính.** Khi có lỗi, thông báo nêu tên persistent property. Ví dụ không cần truy cập field bên cạnh hoặc ép kiểu context sang một implementation riêng.

**Converter không giữ trạng thái theo bản ghi.** Không có field `lastVersion`, `currentEntity` hoặc payload dùng chung. Mỗi lần gọi tự xác định định dạng từ tham số đầu vào.

### 7.2. Giới hạn được chủ động chọn

Converter không tự đoán chuỗi không có tiền tố, không bỏ qua payload hỏng và không biến định dạng chưa biết thành chuỗi rỗng. Các quyết định đó giúp lỗi dữ liệu không bị che bằng một giá trị có vẻ hợp lệ.

Nếu hệ thống thực sự có định dạng legacy không có tiền tố, hãy thêm một nhánh có quy tắc nhận diện rõ, cùng thời hạn hỗ trợ và kế hoạch chuyển đổi. Không dùng một nhánh fallback rộng để nuốt mọi lỗi decode.

## 8. Gắn converter vào đúng thuộc tính

Trong module và phiên bản hỗ trợ cơ chế annotation này, ý định gắn converter có thể được biểu diễn bằng `@ValueConverter`:

```java
import org.springframework.data.convert.ValueConverter;

class Order {

    @ValueConverter(VersionedNoteConverter.class)
    private String deliveryNote;

    private String customerComment;
}
```

Chỉ `deliveryNote` được chỉ định sử dụng converter. `customerComment` không có chỉ định đó trong ví dụ.

Đoạn code chỉ thể hiện phần mapping liên quan, chưa phải entity hay repository hoàn chỉnh cho một store cụ thể. Cần bổ sung định danh, cách tạo object và cấu hình module theo project thực tế.

### 8.1. Annotation không tự tạo hỗ trợ trong module

Để cấu hình có tác dụng, mapper phải hỗ trợ phát hiện annotation và sử dụng cơ chế property conversions tương ứng. Nếu phiên bản/module không có tích hợp đó, việc code biên dịch không bảo đảm giá trị được chuyển đổi khi lưu.

Các thành phần như `PropertyValueConversions` và factory của property converter thuộc phần hạ tầng liên quan. API tạo, kết hợp và đăng ký các thành phần này cần được đối chiếu theo phiên bản/module; không nên áp dụng một đoạn cấu hình bean của store khác chỉ vì tên lớp giống nhau.

### 8.2. Khởi tạo converter và dependency injection

Converter ở ví dụ không có dependency và có thể được tạo bằng constructor không tham số. Điều đó làm giảm yêu cầu đối với cơ chế khởi tạo.

Nếu converter cần một service, phải kiểm tra factory hoặc điểm cấu hình của module có lấy converter từ container hay không. Chỉ gắn một annotation component lên lớp không đủ để khẳng định mapper sẽ sử dụng đúng instance đã được inject.

Cũng không nên giả định mỗi lần chuyển đổi có một converter mới. Thiết kế converter dùng chung an toàn: cấu hình bất biến, biến tạm nằm trong phương thức, và không lưu context của lần gọi vào field.

### 8.3. Không thay thế conversions của module một cách tùy tiện

Nếu module đã cung cấp custom conversions hoặc cấu hình mặc định, việc bổ sung property conversion cần giữ các phần đó theo điểm mở rộng phù hợp. Thay toàn bộ cấu hình có thể làm mất converters hoặc nhận diện kiểu mà store cần.

`SimpleTypeHolder`, custom conversions theo kiểu và property conversions có quan hệ trong hạ tầng mapping, nhưng không phải ba tên gọi cho cùng một registry. Thêm một kiểu vào holder không tự gắn converter cho một property. Gắn converter cho một property cũng không có nghĩa phải thay đổi cách xử lý toàn cục của kiểu Java đó.

## 9. `null`, chuỗi rỗng và property không tồn tại

API `PropertyValueConverter` có các hook `readNull` và `writeNull` để biểu diễn xử lý giá trị null. Khi không ghi đè, hợp đồng mặc định của các hook này giữ kết quả null.

Các phương thức `read` và `write` trong ví dụ được viết cho đầu vào khác null. Không nên gọi trực tiếp chúng với null rồi kết luận đó là hành vi null của toàn bộ hạ tầng mapping.

### 9.1. Chính sách ví dụ

| Trạng thái | Ý nghĩa | Chính sách |
| --- | --- | --- |
| Domain `null` | Không có ghi chú | Giữ null theo null hook và quy tắc của module |
| Domain `""` | Có chuỗi rỗng | Ghi thành `v2:` |
| Stored `v1:` | Phiên bản 1 với nội dung rỗng | Đọc thành `""` |
| Stored `v2:` | Phiên bản 2 với payload rỗng | Đọc thành `""` |
| Stored chuỗi rỗng không tiền tố | Không theo hợp đồng định dạng | Từ chối |
| Property không xuất hiện trong dữ liệu | Không có giá trị tại cấu trúc đó | Phụ thuộc quy tắc đọc của module |

Null và chuỗi rỗng là hai trạng thái khác nhau. Việc store bỏ field null, lưu null tường minh hay áp dụng default value không được quyết định chỉ bởi code converter này.

### 9.2. Missing không mặc định tương đương gọi `readNull`

Một projection có thể không lấy thuộc tính. Một document có thể thiếu field. Một row có thể có cột null. Các trường hợp đó không nhất thiết đi qua cùng một nhánh của mapper.

Nếu ứng dụng cần phân biệt missing, null và empty, phải kiểm tra cách module biểu diễn chúng và kiểm tra đúng loại truy vấn/projection đang sử dụng. Không mặc định mọi property thiếu đều làm converter được gọi.

### 9.3. Sentinel cần được cân nhắc riêng

Có thể thiết kế `writeNull` thành một giá trị sentinel khi API/module cho phép, nhưng khi đó sentinel trở thành một phần của schema dữ liệu. Cần ngăn xung đột với giá trị hợp lệ và kiểm tra cách query diễn đạt null.

Ví dụ hiện tại giữ null để tránh thêm một trạng thái dữ liệu không cần thiết.

## 10. Đọc tương thích không đồng nghĩa truy vấn tương thích

Đây là điểm dễ bỏ sót nhất trong quá trình chuyển phiên bản dữ liệu.

Giả sử store có cả hai bản ghi:

```text
Bản ghi A: deliveryNote = v1:hello
Bản ghi B: deliveryNote = v2:aGVsbG8
```

Đọc cả hai qua converter đều tạo domain value `hello`. Tuy nhiên, query equality thường so sánh với biểu diễn đang được lưu, chứ không đọc từng bản ghi rồi gọi converter để so sánh ở Java.

Nếu đường query của module sử dụng conversion theo hướng ghi, tham số `hello` sẽ thành `v2:aGVsbG8`. Khi đó, bản ghi A có thể không được tìm thấy bằng một phép equality duy nhất.

| Khả năng | Có được bảo đảm chỉ nhờ converter đọc cả hai phiên bản? |
| --- | --- |
| Đọc bản ghi `v1` thành domain | Có, nếu đường đọc gọi converter và dữ liệu hợp lệ |
| Đọc bản ghi `v2` thành domain | Có, với cùng điều kiện |
| Equality query tìm cả `v1` và `v2` | Không |
| Sort theo thứ tự chuỗi domain | Không |
| Query theo tiền tố nội dung domain | Không |
| Index cũ tự chuyển sang định dạng mới | Không |

### 10.1. Kiểm tra từng đường truy vấn

Một phương thức derived query, một query viết tay, một aggregation và một projection có thể có cách mapping giá trị khác nhau. Không suy ra hành vi của tất cả chúng chỉ từ việc `save` và `findById` đã hoạt động.

Với mỗi đường ứng dụng sử dụng, cần biết:

- Tham số query có đi qua property conversion không?
- Converter được chọn dựa vào property nào?
- Kết quả trả về có được materialize thành property domain không?
- Update từng field hoặc thao tác trực tiếp của driver có bỏ qua converter không?

### 10.2. Chiến lược chuyển tiếp cho query

Tùy khả năng của store và yêu cầu ứng dụng, có thể chọn:

- Backfill dữ liệu cũ để query dùng một biểu diễn thống nhất.
- Dùng điều kiện truy vấn rõ ràng cho cả biểu diễn cũ và mới trong thời gian chuyển tiếp.
- Bổ sung trường tìm kiếm có định dạng ổn định nếu hợp đồng ứng dụng cần điều đó.

Mỗi lựa chọn có tác động đến index và tính tương thích. Việc xây query nhiều biểu diễn phải tính đến cách module xử lý tham số để tránh converter biến đổi lại một chuỗi vốn đã được định dạng sẵn.

Với sort và range query, Base64 không bảo toàn thứ tự từ điển của chuỗi domain. Nếu cần các thao tác đó, phải chọn biểu diễn lưu trữ phục vụ được nhu cầu hoặc thiết kế một trường dữ liệu thích hợp.

## 11. Kế hoạch chuyển dữ liệu từ `v1` sang `v2`

Một lộ trình chuyển tiếp có thể gồm:

1. Triển khai reader hiểu cả `v1` và `v2`.
2. Bảo đảm các phiên bản ứng dụng còn đang phục vụ có thể đọc định dạng sẽ được ghi.
3. Chuyển writer sang `v2` tại thời điểm đã bảo đảm tương thích.
4. Xử lý yêu cầu query trong giai đoạn dữ liệu còn nhiều phiên bản.
5. Backfill các giá trị `v1` còn tồn tại theo cách an toàn với cập nhật đồng thời.
6. Xác nhận dữ liệu cũ đã được xử lý trước khi cân nhắc bỏ hỗ trợ đọc `v1`.

Đây là các giai đoạn logic; số lần phát hành phụ thuộc hệ thống. Ví dụ converter trong bài là trạng thái reader đã hỗ trợ cả hai và writer đã chọn `v2`. Nó chưa đủ để tự giải quyết triển khai cuốn chiếu với ứng dụng cũ chỉ hiểu `v1`.

### 11.1. Đừng ghi đè cập nhật nghiệp vụ trong lúc backfill

Tác vụ chuyển dữ liệu có thể đọc một giá trị cũ, sau đó ghi lại trong lúc người dùng đã sửa ghi chú. Nếu không có điều kiện bảo vệ phù hợp, nó có thể khôi phục nội dung cũ lên bản ghi mới.

Cần sử dụng điều kiện cập nhật hoặc cơ chế concurrency của store theo thiết kế. Nếu dùng `@Version`, phải hiểu đường cập nhật đang chạy có thực thi kiểm tra version của module hay không; thao tác driver trực tiếp có thể có hợp đồng khác với repository save.

### 11.2. Đọc không tự làm dữ liệu được nâng cấp

Converter `read` trả về domain value; nó không tự ghi lại bản ghi thành `v2`. Chỉ đọc một entity không phải một tác vụ migration.

Ngay cả việc gọi save sau đó có ghi lại field này hay không cũng phụ thuộc module, kiểu thao tác và chiến lược cập nhật. Không lấy hiệu ứng ngẫu nhiên của một luồng nghiệp vụ làm kế hoạch backfill duy nhất.

### 11.3. Rollback cần khả năng đọc định dạng mới

Nếu bản cũ chỉ đọc `v1`, rollback sau khi bản mới ghi `v2` có thể khiến ứng dụng không đọc được dữ liệu. Kế hoạch phát hành cần xác định cửa sổ tương thích và khả năng phục hồi trước khi đổi writer.

## 12. Kiểm chứng ở ba tầng

Các tình huống sau là hướng dẫn khi triển khai trên project thực tế; bài học không báo cáo kết quả đã chạy trên một store cụ thể.

### 12.1. Tầng logic chuyển đổi

| Đầu vào hoặc thao tác | Kết quả mong đợi |
| --- | --- |
| `read("v1:hello", context)` | `hello` |
| `read("v2:aGVsbG8", context)` | `hello` |
| `write("hello", context)` | `v2:aGVsbG8` |
| `read(write(text, context), context)` | Bằng `text` với chuỗi Unicode hợp lệ |
| `read("v3:hello", context)` | Lỗi định dạng chưa được hỗ trợ |
| `read("hello", context)` | Lỗi thiếu phiên bản |
| `read("v2:%%%", context)` | Lỗi payload |
| `read("v2:_w", context)` | Lỗi do byte không tạo thành UTF-8 hợp lệ |
| `readNull(context)` theo mặc định | Null |
| `writeNull(context)` theo mặc định | Null |

Khi kiểm tra nhánh lỗi của converter, context phải cung cấp metadata property vì code dùng tên property để xây thông báo. Test không nên bỏ context rồi bỏ qua luôn đường xử lý lỗi.

### 12.2. Tầng tích hợp mapping

Một kịch bản hữu ích cần xác nhận:

- Lưu `deliveryNote` làm thay đổi biểu diễn đúng như hợp đồng.
- `customerComment` không có chỉ định converter vẫn được xử lý theo mapping thông thường.
- Đọc bản ghi `v1` và `v2` tạo đúng giá trị domain.
- Null, chuỗi rỗng và property thiếu được xử lý theo quy tắc đã chọn.
- Converter thực sự được lấy từ factory/cấu hình mong muốn.

Chỉ kiểm tra instance converter trực tiếp không phát hiện được lỗi annotation không được module hỗ trợ hoặc lỗi mapper dùng một cấu hình khác.

### 12.3. Tầng truy vấn và triển khai

Kiểm tra trên dữ liệu có cả hai phiên bản:

- Derived query hoặc query mà ứng dụng thực sự sử dụng.
- Projection có và không có `deliveryNote`.
- Cập nhật từng field, bulk update hoặc đường driver trực tiếp nếu có.
- Query cần dùng index và hành vi sort/range.
- Kịch bản bản ứng dụng cũ đọc dữ liệu do bản mới ghi trong thời gian phát hành.

Mục đích là kiểm chứng hợp đồng ứng dụng, không chỉ xác nhận một phương thức converter trả về đúng chuỗi.

## 13. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân cần xem xét | Cách khoanh vùng |
| --- | --- | --- |
| Annotation có trong code nhưng dữ liệu vẫn giữ nguyên | Module/phiên bản không tích hợp property conversion, hoặc đường ghi bỏ qua mapper | Xác định mapper và điểm đăng ký thực tế |
| Nhiều field chuỗi bị đổi định dạng | Dùng conversion theo kiểu trên phạm vi quá rộng | Kiểm tra phạm vi đăng ký và property được chỉ định |
| Converter không có dependency cần thiết | Factory tạo instance khác với instance trong container | Kiểm tra cách khởi tạo và khả năng bean lookup |
| Converter cần field bên cạnh nhưng không lấy được | Context không hỗ trợ hoặc đường đọc không có field đó | Đánh giá hợp đồng context và thiết kế nguồn phiên bản |
| Đọc được dữ liệu cũ nhưng query không tìm thấy | Dữ liệu có nhiều biểu diễn lưu trữ | Kiểm tra tham số sau mapping và kế hoạch migration |
| Null gây lỗi khi gọi trực tiếp converter | Đã bỏ qua null hook trong cách kiểm tra | Kiểm tra riêng hợp đồng null và cách mapper gọi |
| Lỗi đệ quy hoặc stack overflow | Delegate trở lại cùng đường conversion | Xác định đường gọi và điều kiện dừng |
| Kết quả phụ thuộc bản ghi trước đó | Converter lưu trạng thái theo request/entity trong field dùng chung | Chuyển trạng thái tạm về phạm vi lần gọi |
| Nâng dependency xong phát sinh lỗi liên kết API | Lệch phiên bản Commons và module store | Khôi phục tập dependency tương thích |

Không nên chữa lỗi bằng cách âm thầm trả lại dữ liệu gốc trong mọi trường hợp. Với định dạng có phiên bản, fallback không kiểm soát có thể biến dữ liệu sai thành một giá trị domain tưởng như hợp lệ.

## 14. Tự kiểm tra mức hiểu

**Vì sao `Converter<String, String>` dùng chung có thể không phù hợp với ví dụ?**

Vì nhu cầu chỉ thuộc về `deliveryNote`. Một cặp kiểu quá rộng không tự thể hiện field nào cần định dạng riêng. Property conversion biểu diễn phạm vi đó rõ hơn trong module có hỗ trợ.

**Context có tự cho biết phiên bản schema của toàn bộ bản ghi không?**

Không có bảo đảm chung như vậy. Cần một nguồn phiên bản cụ thể và khả năng truy cập được module hỗ trợ. Trong ví dụ, phiên bản nằm ngay trong giá trị lưu trữ.

**Có thể dùng `@Version` để chọn thuật toán decode thay cho tiền tố không?**

Không nên đồng nhất hai cơ chế. `@Version` phục vụ concurrency theo hợp đồng của module, còn phiên bản định dạng là hợp đồng đọc dữ liệu do ứng dụng thiết kế.

**Chỉ có annotation `@ValueConverter` là đã đủ để kết luận tính năng hoạt động chưa?**

Chưa. Phải có module/phiên bản hỗ trợ, cấu hình khởi tạo và đường mapping thực sự sử dụng converter.

**Tại sao đọc được `v1` và `v2` vẫn chưa đủ cho equality query?**

Vì query thường so sánh biểu diễn lưu trữ. Hai biểu diễn khác nhau có thể tạo cùng giá trị domain sau khi đọc nhưng vẫn khác nhau khi store so sánh.

**Đổi writer sang `v2` có tự chuyển toàn bộ dữ liệu cũ không?**

Không. Dữ liệu cũ cần được xử lý bằng kế hoạch cập nhật/backfill phù hợp, có tính đến query và cập nhật đồng thời.

## 15. Nguyên tắc áp dụng

Dùng `PropertyValueConverter` khi một persistent property cần hợp đồng chuyển đổi riêng và module hiện tại có hỗ trợ phù hợp. Xác định rõ kiểu domain, kiểu biểu diễn, hướng đọc/ghi và cách xử lý null trước khi cấu hình.

Sử dụng context theo đúng khả năng đã được xác nhận của phiên bản/module; không mặc định nó chứa toàn bộ entity hoặc trạng thái ứng dụng. Khi biểu diễn dữ liệu có phiên bản, thiết kế riêng khả năng đọc dữ liệu cũ, chính sách ghi mới, query và migration.

Một triển khai đầy đủ cần thống nhất **phạm vi thuộc tính, logic chuyển đổi, tích hợp store và khả năng tương thích dữ liệu**. Việc một converter biên dịch hoặc chuyển đổi đúng khi gọi trực tiếp mới chỉ xác nhận một phần của hợp đồng đó.