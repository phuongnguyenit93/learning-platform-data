# Tắt DTD hoặc thực thể ngoài khi không cần trong StAX (Java)

## 1. Mục tiêu và trường hợp sử dụng

Khi một ứng dụng Java nhận XML từ HTTP upload, message queue, dịch vụ tích hợp, file do khách hàng gửi hoặc một nguồn chưa được tin cậy, chỉ việc chọn parser StAX không có nghĩa là XML tự động an toàn. Tài liệu XML có thể chứa **DOCTYPE/DTD**, khai báo **entity nội bộ**, **entity ngoài** trỏ đến file hoặc URL và các cấu trúc khiến parser tiêu thụ quá nhiều tài nguyên.

Trong nhiều hệ thống, nghiệp vụ chỉ cần đọc các phần tử, thuộc tính và text của XML. **Không có yêu cầu hợp lệ nào phải tải DTD hoặc mở entity từ hệ thống file/network**. Khi đó nguyên tắc an toàn là:

> **Tắt xử lý DTD và tắt phân giải external entities trước khi tạo bất kỳ XML reader nào. Nếu chính sách cấm DOCTYPE hoàn toàn, phải có cơ chế thực sự từ chối DOCTYPE, không chỉ bỏ qua nội dung DTD.**

Đó là trọng tâm bài **“Tắt DTD hoặc thực thể ngoài khi không cần”**, thuộc **StAX nâng cao**.

Sau bài, bạn có thể:

1. Phân biệt `DOCTYPE`, DTD nội bộ/ngoài, general entity, parameter entity và năm predefined XML entities.
2. Hiểu các nguy cơ **XXE**, SSRF, đọc file cục bộ và XML entity expansion.
3. Cấu hình đúng `XMLInputFactory.SUPPORT_DTD=false` và `XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES=false`.
4. Dùng `XMLConstants.ACCESS_EXTERNAL_DTD=""` trên implementation hỗ trợ và `XMLResolver` từ chối tài nguyên ngoài theo nguyên tắc fail closed.
5. Phân biệt **ignore DTD** với **reject DTD**; biết tùy chọn JDK 22+ `jdk.xml.dtd.support=deny`.
6. Áp dụng cấu hình bảo mật cho **cả `XMLStreamReader` và `XMLEventReader`**.
7. Nhận diện lỗi cấu hình có thể khiến parser chạy thiếu bảo vệ; không đánh đồng các property có tên gần giống.
8. Bổ sung giới hạn bytes, độ sâu, events, text và thời gian vì tắt DTD chưa chặn hết XML denial of service.
9. Phân biệt việc đóng StAX reader với ownership của `Reader/InputStream` đầu vào.
10. Chạy chương trình Java 17+ với parser StAX thật, kiểm thử tài liệu hợp lệ và các mẫu DTD/entity nguy hiểm.

**Phạm vi hiện hành:** Những API trong `javax.xml.stream` thuộc module `java.xml` vẫn được dùng trên Java SE 26. Ví dụ chạy với `--release 17`, đã được biên dịch và thực thi bằng OpenJDK 24. Hai cách chạy, bình thường và với `-Djdk.xml.dtd.support=deny`, đều vượt qua **29/29 kiểm thử**.

## 2. DTD và entities là gì?

### 2.1. DOCTYPE và DTD

Một XML có thể có khai báo DOCTYPE ở phần đầu:

```xml
<?xml version="1.0"?>
<!DOCTYPE invoice [
  <!ELEMENT invoice (number)>
  <!ELEMENT number (#PCDATA)>
]>
<invoice>
  <number>INV-001</number>
</invoice>
```

`<!DOCTYPE ...>` có thể mang một **internal subset** gồm các khai báo như `<!ELEMENT>`, `<!ATTLIST>` và `<!ENTITY>`. Nó cũng có thể tham chiếu **external subset** bằng `SYSTEM` hoặc `PUBLIC`.

Ví dụ DTD bên ngoài:

```xml
<!DOCTYPE invoice SYSTEM "https://example.invalid/invoice.dtd">
<invoice><number>INV-001</number></invoice>
```

Nếu ứng dụng **không cần DTD** để làm nhiệm vụ, việc cho parser xử lý DTD sẽ mở ra một nhóm khả năng không cần thiết. Đó là lý do nên tắt nó ngay từ cấu hình factory.

### 2.2. General entity nội bộ

Một DTD có thể khai báo entity rồi tham chiếu bằng `&name;`:

```xml
<!DOCTYPE root [
  <!ENTITY greet "Xin chào">
]>
<root>&greet;</root>
```

Khi DTD processing được bật, parser có thể biến `&greet;` thành chuỗi `Xin chào`. Với input không đáng tin và không cần DTD, tốt nhất là **không xử lý kiểu khai báo này**.

### 2.3. External entity

Entity ngoài trỏ đến một tài nguyên khác:

```xml
<!DOCTYPE root [
  <!ENTITY ext SYSTEM "file:///not-a-real-secret">
]>
<root>&ext;</root>
```

Đây là **mẫu minh họa bị từ chối**, không phải một resource có thật. Nếu parser tự lấy nội dung từ file hoặc URL theo identifier do người dùng kiểm soát, nó có thể tạo rủi ro **đọc file cục bộ**, **SSRF** hoặc rò rỉ dữ liệu.

Một DOCTYPE cũng có thể trỏ thẳng đến DTD ở URL:

```xml
<!DOCTYPE root SYSTEM "https://example.invalid/not-fetched.dtd">
<root/>
```

Với source không tin cậy, ứng dụng không nên tự mở URL chỉ vì nó xuất hiện trong XML.

### 2.4. Parameter entity và external subset

DTD còn có **parameter entities** được biểu diễn bằng ký hiệu `%name;` bên trong DTD. Chúng có thể tham chiếu những khai báo hoặc tài nguyên khác; chỉ chặn general external entity mà bỏ qua external DTD/parameter entities là chưa đủ cho một cấu hình bảo vệ tổng thể.

**Chính sách đơn giản khi không cần DTD:** không cho DTD processing, không cho external entity resolution, không cho external DTD access và (nếu cần reject tuyệt đối) từ chối DOCTYPE.

### 2.5. Năm predefined XML entities vẫn nên dùng được

XML có năm predefined entities:

| Entity | Ký tự tương ứng |
| --- | --- |
| `&amp;` | `&` |
| `&lt;` | dấu nhỏ hơn |
| `&gt;` | dấu lớn hơn |
| `&quot;` | dấu nháy kép |
| `&apos;` | dấu nháy đơn |

Đây là các thực thể có sẵn theo XML, **không cần DTD do người dùng khai báo**. Tắt DTD hoặc external entities **không có nghĩa** phải từ chối các biểu diễn escape text hợp lệ như `&amp;`.

Ví dụ XML hợp lệ:

```xml
<root>
  <name>Xin chào &amp; Java 🌿</name>
</root>
```

Sau parsing, text có thể là `Xin chào & Java 🌿`.

Cần phân biệt entity references với văn bản nằm trong CDATA:

```xml
<root>
  <safe><![CDATA[<not-an-element>]]></safe>
</root>
```

`<![CDATA[...]]>` không phải khai báo DTD và nội dung bên trong là text. Cấu hình an toàn của bài vẫn đọc được CDATA.

## 3. Tại sao tắt DTD và external entity quan trọng?

### 3.1. XXE: XML External Entity Injection

**XXE** xảy ra khi một XML processor cho tài liệu không đáng tin điều khiển việc giải tham chiếu entity ngoài. Rủi ro gồm:

- Đọc file hoặc metadata mà tiến trình Java có quyền truy cập.
- Mở kết nối đến địa chỉ nội bộ ngoài ý muốn (**SSRF**).
- Gửi request đến host không được phép.
- Rò rỉ nội dung qua lỗi, output hay các side effects khác.
- Đẩy parser hoặc hệ thống vào tình trạng quá tải.

Không phải parser nào cũng tự truy cập tài nguyên trong mọi cấu hình; vấn đề ở đây là **không nên dựa vào default của provider**. Java SE 26 `XMLInputFactory` ghi default của `IS_SUPPORTING_EXTERNAL_ENTITIES` là *unspecified*, còn `SUPPORT_DTD` mặc định cho phép DTD. Cần đặt các giá trị bảo mật **tường minh**.

### 3.2. Entity expansion và XML bomb

DTD nội bộ có thể khai báo entity được lồng nhiều cấp và khiến việc mở rộng text tăng rất nhanh. Một bộ mở rộng entity không có limits có thể dùng nhiều CPU/RAM. Mẫu “billion laughs” là tên thường gặp của nhóm kỹ thuật này.

Bài **không chạy payload tấn công thực tế**. Ví dụ kiểm thử chỉ có một entity nhỏ để xác nhận rằng chính sách từ chối DTD được áp dụng ngay từ đầu, chứ không đợi đến khi parser mở rộng entity.

### 3.3. Tắt DTD không giải quyết mọi DoS

Vẫn còn các loại input nguy hiểm không cần DTD:
- XML với **độ sâu** rất lớn.
- Vô số phần tử/sự kiện.
- Một text node khổng lồ.
- Tài liệu rất lớn hoặc nén có tỷ lệ giải nén lớn.
- Nguồn mạng đọc không kết thúc, không có deadline.
- Các attributes, names hoặc structures có kích thước vượt budget.

Do đó cần kết hợp **input byte budget**, **processing time budget** và **giới hạn sự kiện/độ sâu/nội dung**, không chỉ hai flags StAX.

## 4. Hai property StAX cốt lõi

### 4.1. `XMLInputFactory.SUPPORT_DTD`

```java
factory.setProperty(XMLInputFactory.SUPPORT_DTD, false);
```

Property tương ứng với tên chuẩn `javax.xml.stream.supportDTD`. Giá trị `false` yêu cầu parser không xử lý DTD. Đây là setting đầu tiên nên chọn khi ứng dụng không cần DTD.

**Cảnh báo:** “Không xử lý” **không đồng nghĩa** “nhìn thấy DOCTYPE là ném exception” trong mọi StAX implementation. Một parser có thể **bỏ qua DTD** và vẫn tiếp tục xử lý phần XML còn lại. Nếu business/security policy yêu cầu **từ chối tài liệu chứa DOCTYPE**, cần một lớp kiểm tra bổ sung phù hợp với JDK/provider đang dùng.

### 4.2. `XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES`

```java
factory.setProperty(
        XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES,
        false);
```

Property tương ứng tên chuẩn `javax.xml.stream.isSupportingExternalEntities`, điều khiển hỗ trợ **external parsed entities**.

**Không được coi đây là sự thay thế hoàn toàn cho `SUPPORT_DTD=false`.** Nếu vẫn cho DTD nội bộ, parser có thể xử lý các internal entities hoặc khai báo khác. Đối với một ứng dụng **không cần DTD**, đặt **cả hai property thành false**.

### 4.3. Tại sao phải thiết lập trước khi tạo reader?

`XMLInputFactory` dùng configuration hiện tại để tạo `XMLStreamReader` hoặc `XMLEventReader`. Cần:

```text
Create XMLInputFactory
        |
        v
Set SUPPORT_DTD = false
        |
        v
Set IS_SUPPORTING_EXTERNAL_ENTITIES = false
        |
        v
Deny external DTD protocols and resolver
        |
        v
Create XMLStreamReader / XMLEventReader
        |
        v
Read events with DOCTYPE policy
```

Không cấu hình factory **sau** khi reader đã tạo rồi kỳ vọng reader cũ nhận tất cả các thay đổi. Hãy tạo factory đã harden trước, sau đó sinh reader từ nó.

### 4.4. `getProperty` và `isPropertySupported`

Bạn có thể dùng `factory.getProperty(name)` để xác nhận trạng thái đã cấu hình, hoặc `factory.isPropertySupported(name)` để kiểm tra implementation.

Tuy nhiên:
- `isPropertySupported(...)` chỉ cho biết property được nhận diện, **không chứng minh parser đang bị tấn công sẽ không tải tài nguyên**.
- `getProperty(...)` là một kiểm tra cấu hình tốt, nhưng **không thay thế test với XML nguy hiểm**.
- Một provider không hỗ trợ security setting có thể ném `IllegalArgumentException` khi `setProperty`. **Fail closed**: đừng catch rồi tiếp tục parsing.

## 5. Bổ sung hạn chế external DTD access và deny resolver

### 5.1. `XMLConstants.ACCESS_EXTERNAL_DTD`

Trên JDK built-in JAXP provider, bạn có thể đặt:

```java
factory.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
```

Giá trị chuỗi rỗng có nghĩa không cho phép external DTD access theo cơ chế external-access property. Trong chương trình đã kiểm thử trên OpenJDK 24, `getProperty(XMLConstants.ACCESS_EXTERNAL_DTD)` trả đúng chuỗi rỗng.

**Tính tương thích:** Đây là JAXP external-access property, không phải một trong hai constants cốt lõi được định nghĩa trực tiếp trên `XMLInputFactory`. Hãy kiểm tra provider thực tế và **đừng bỏ qua lỗi unsupported**; không mặc định mọi StAX provider đều hỗ trợ nó như JDK built-in implementation.

Không nhầm `ACCESS_EXTERNAL_DTD` với `ACCESS_EXTERNAL_SCHEMA` hoặc `ACCESS_EXTERNAL_STYLESHEET`. Schema validation và XSLT transformation có các API/cài đặt security **riêng**, không tự được bảo vệ hoàn toàn chỉ vì StAX reader an toàn.

### 5.2. `XMLResolver` từ chối mọi external resource

`javax.xml.stream.XMLResolver` cho phép StAX processor yêu cầu một tài nguyên ngoài qua:

```java
Object resolveEntity(
        String publicID,
        String systemID,
        String baseURI,
        String namespace)
        throws XMLStreamException;
```

Đây là chữ ký của interface minh họa. Nếu ứng dụng không cho phép tải external resources, resolver có thể ném exception:

```java
factory.setXMLResolver(
        (publicId, systemId, baseUri, namespace) -> {
            throw new XMLStreamException(
                    "External resource resolution is prohibited");
        });
```

**Vì sao throw thay vì return null?** Theo cơ chế resolver, trả `null` có thể khiến parser dùng cách giải quyết mặc định. Trả `null` **không phải deny-all policy**. Ném `XMLStreamException` đảm bảo request giải tham chiếu bị từ chối trong code này.

**Lưu ý:** Một resolver không được gọi không nhất thiết là bằng chứng độc lập rằng mọi tài nguyên đã được chặn: parser có thể không cố resolve do DTD đã bị disable. Cần kiểm thử kết hợp policy, provider và input. Trong fixture, không có bất kỳ callback resolver nào được gọi cho các mẫu kiểm thử.

### 5.3. Resolver không chặn nguồn đầu vào ban đầu

Nếu ứng dụng chủ động mở:

```java
InputStream input = url.openStream();
XMLStreamReader reader = factory.createXMLStreamReader(input);
```

thì **yêu cầu network ban đầu đã xảy ra trước khi XML parser xử lý**. External entity controls không ngăn hành động mở URL đầu vào đó. Đây là snippet minh họa một nguy cơ thiết kế: dùng source do caller sở hữu và áp dụng URL allowlist, network policies hoặc đường dẫn storage hợp lệ **trước khi** truyền stream vào parser.

Với XML upload, ưu tiên lấy `InputStream` được framework cấp từ request đã qua giới hạn kích thước, thay vì tin một `systemId` có thể là đường dẫn/URL do client cung cấp.

## 6. Ignore DTD khác reject DOCTYPE

Đây là phân biệt quan trọng nhất của bài.

| Chính sách | Ý nghĩa | Hành động |
| --- | --- | --- |
| **Disable DTD processing** | Không xử lý declaration/subset | `SUPPORT_DTD=false` |
| **Disable external entities** | Không phân giải external parsed entities | `IS_SUPPORTING_EXTERNAL_ENTITIES=false` |
| **Deny external DTD access** | Không cho các external protocols | `ACCESS_EXTERNAL_DTD=""` nếu provider hỗ trợ |
| **Deny resolver** | Từ chối mọi resolver callback | `setXMLResolver` với exception |
| **Reject DOCTYPE** | Tài liệu có DOCTYPE phải fail | JDK 22+ `jdk.xml.dtd.support=deny`, hoặc cơ chế reject có bảo đảm theo provider/pipeline |

### 6.1. Kiểm tra event `DTD`

StAX cung cấp `XMLStreamConstants.DTD`. Với cursor:

```java
int event = reader.next();
if (event == XMLStreamConstants.DTD) {
    throw new XMLStreamException(
            "DOCTYPE is forbidden",
            reader.getLocation());
}
```

Với event API:

```java
XMLEvent event = events.nextEvent();
if (event.getEventType() == XMLStreamConstants.DTD) {
    throw new XMLStreamException(
            "DOCTYPE is forbidden",
            event.getLocation());
}
```

Hai đoạn là snippets đặt trong loop và trong phạm vi readers đã tạo.

**Giới hạn cần nói rõ:** Một provider có thể **bỏ qua DTD mà không cung cấp event `DTD`** khi `SUPPORT_DTD=false`. Kiểm tra DTD event là *defense in depth*, nhưng **không phải một cơ chế reject DOCTYPE portable tuyệt đối** cho mọi provider. Nếu contract nghiệp vụ bắt buộc reject trên mọi XML, hãy kiểm tra provider thực tế hoặc dùng một bước parser/validation riêng có chính sách reject DOCTYPE rõ.

### 6.2. JDK 22+ có `jdk.xml.dtd.support=deny`

JAXP Security Guide hiện hành mô tả property `jdk.xml.dtd.support` với ba giá trị:

| Giá trị | Hành vi |
| --- | --- |
| `allow` | Cho phép DTD processing (giá trị mặc định của setting này) |
| `ignore` | Bỏ qua DTD |
| `deny` | **Từ chối DTD như một lỗi** |

Trên **JDK 22 trở lên**, có thể cấu hình JDK system property, ví dụ:

```bash
java -Djdk.xml.dtd.support=deny StaxDtdGuardDemo
```

Lệnh này đã được kiểm thử trên OpenJDK 24. Nó là **JDK-specific setting**, không phải `XMLInputFactory` constant portable được bảo đảm trên mọi provider. Nếu dự án biên dịch target Java 17 và chạy Java 17, **không được dựa vào `jdk.xml.dtd.support`** như thể nó đã tồn tại và hoạt động từ bản 17.

Cần phân biệt:
- `SUPPORT_DTD=false`: API StAX portable, không xử lý DTD.
- `jdk.xml.dtd.support=deny`: JDK property mới hơn, từ chối DTD ở tầng JAXP processor hỗ trợ property.
- Event-level rejection: additional check khi reader phát DTD event.

**Đừng viết** một regex kiểu `xml.contains("<!DOCTYPE")` để coi đó là parser security policy: chuỗi đó có thể xuất hiện hợp lệ trong comment/CDATA; lexical variants và input encodings khác nhau làm regex filter dễ sai. Fixture sẽ cho thấy `<!DOCTYPE` trong comment không phải DTD declaration.

## 7. Phân biệt các security settings có tên gần giống

| Setting | Có phải lựa chọn phù hợp cho StAX? | Vì sao |
| --- | --- | --- |
| `XMLInputFactory.SUPPORT_DTD=false` | **Có** | Không xử lý DTD |
| `XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES=false` | **Có** | Không resolve external parsed entities |
| `XMLConstants.ACCESS_EXTERNAL_DTD=""` | **Có trên provider hỗ trợ** | Hạn chế external DTD access protocols |
| `XMLResolver` reject-all | **Có** | Fail closed khi yêu cầu resolution |
| `jdk.xml.dtd.support=deny` | **Có trên JDK hỗ trợ (22+)** | Reject DTD thay vì ignore |
| `XMLInputFactory.IS_REPLACING_ENTITY_REFERENCES=false` | **Không dùng làm kiểm soát XXE chính** | Điều khiển cách entity references được báo/thay thế, không tự chặn external DTD |
| `XMLConstants.FEATURE_SECURE_PROCESSING` | **Không phải property StAX chuẩn để set trên `XMLInputFactory`** | DOM/SAX/Schema/Transformer có cấu hình riêng |
| `SAXParserFactory` feature `disallow-doctype-decl` | **Không đặt trực tiếp trên XMLInputFactory** | Thuộc SAX/DOM parser configuration |
| `TransformerFactory` external stylesheet restriction | **Cần ở XSLT layer, không thay StAX settings** | Stylesheet imports/includes và `document()` có đường tải riêng |
| `SchemaFactory` external schema restriction | **Cần ở validation layer, không thay StAX settings** | Validator/schema loading riêng |

Một anti-pattern thường gặp:

```java
factory.setProperty(
        XMLInputFactory.IS_REPLACING_ENTITY_REFERENCES,
        false);
// Sai nếu coi dòng này là biện pháp chặn XXE đầy đủ.
```

Property này không thay được việc tắt DTD, external entities, external access và resolver.

## 8. Cấu hình an toàn có thể dùng lại

Trong Java 17+ và JDK default provider, một factory cấu hình rõ là:

```java
static XMLInputFactory secureFactory() {
    XMLInputFactory factory =
            XMLInputFactory.newDefaultFactory();

    factory.setProperty(
            XMLInputFactory.IS_NAMESPACE_AWARE, true);
    factory.setProperty(
            XMLInputFactory.SUPPORT_DTD, false);
    factory.setProperty(
            XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES,
            false);
    factory.setProperty(
            XMLConstants.ACCESS_EXTERNAL_DTD, "");
    factory.setXMLResolver(
            (publicId, systemId, baseUri, namespace) -> {
                throw new XMLStreamException(
                        "External resource resolution is prohibited");
            });

    return factory;
}
```

Đây là method Java minh họa sử dụng imports `javax.xml.stream.*` và `javax.xml.XMLConstants`. Nó giả định dùng JDK built-in provider. Trong ứng dụng thực tế:

1. Tạo factory trước khi nhận input.
2. Set **tất cả** các controls cần thiết.
3. Không catch `IllegalArgumentException` rồi bỏ qua.
4. Tạo readers từ factory đã kiểm soát.
5. Nếu policy là reject DOCTYPE, bổ sung một rejection mechanism có bảo đảm cho provider (JDK 22+ property hoặc pipeline phù hợp).
6. Dùng parser theo trust boundary: đừng chia sẻ một factory đang bị thay đổi properties đồng thời giữa nhiều threads mà không kiểm soát.
7. Đóng reader và nguồn đầu vào theo ownership.
8. Giới hạn bytes, thời gian, độ sâu, event count và text.

### 8.1. Vì sao `newDefaultFactory()`?

`XMLInputFactory.newDefaultFactory()` chọn **built-in system-default implementation** của JDK, thích hợp cho ví dụ có thể tái lập trên JDK. `XMLInputFactory.newFactory()`/`newInstance()` có thể chịu cơ chế JAXP provider lookup và chọn third-party provider.

Nếu production dùng Woodstox, Aalto hoặc một provider khác, hãy kiểm tra tài liệu và integration tests của **đúng version**. Chỉ compile thành công không đủ chứng minh provider sẽ chặn mọi external access như mong đợi.

### 8.2. Giới hạn của `ACCESS_EXTERNAL_DTD`

Theo JAXP security guidance, external-access properties điều khiển **protocol access** và không tự là allowlist cho từng host/path. Nếu hệ thống cần cho phép một vài resources hợp lệ, cân nhắc XML catalog/resolver strict với **nguồn local đã được phê duyệt** thay vì bật chung `http`, `https` hoặc `file`. Trường hợp này phải có threat-model riêng.

Nếu bạn **không cần DTD**, không có lý do bật lại external protocols; hướng đơn giản nhất là **deny all**.

## 9. Đọc XML với `XMLStreamReader` và `XMLEventReader`

### 9.1. Cursor API

`XMLStreamReader` đọc XML theo `next()` và trả constants như `START_ELEMENT`, `CHARACTERS`, `END_ELEMENT`, `DTD`. Đoạn xử lý nên kiểm tra:

```java
while (reader.hasNext()) {
    int event = reader.next();

    if (event == XMLStreamConstants.DTD) {
        throw new XMLStreamException(
                "DTD forbidden", reader.getLocation());
    }

    if (event == XMLStreamConstants.ENTITY_REFERENCE) {
        throw new XMLStreamException(
                "Unexpected entity reference", reader.getLocation());
    }

    // Xử lý start/end/text trong limits.
}
```

Phần `ENTITY_REFERENCE` là một bước kiểm tra bổ sung cho policy cụ thể; nó không thể thay các factory settings. Với mặc định thay thế predefined entities, `&amp;` sẽ đi vào text bình thường. Đừng từ chối toàn bộ ký tự `&` đã được escape hợp lệ trong XML.

### 9.2. Event API

`XMLEventReader` trả các event objects có `event.getEventType()` và `event.getLocation()`:

```java
while (events.hasNext()) {
    XMLEvent event = events.nextEvent();

    if (event.getEventType() == XMLStreamConstants.DTD) {
        throw new XMLStreamException(
                "DTD forbidden", event.getLocation());
    }

    if (event.isEntityReference()) {
        throw new XMLStreamException(
                "Unexpected entity reference", event.getLocation());
    }
}
```

Dùng **chính factory đã harden** để tạo event reader. Nếu application sử dụng một wrapper khác tự tạo StAX provider mới, hãy xác minh wrapper nhận reader đã cấu hình thay vì âm thầm parse raw InputStream theo default.

### 9.3. Không nên parse lại để xử lý XML lỗi

Nếu XML bị từ chối vì DTD, không thử parse lần hai bằng cách bật `SUPPORT_DTD=true` để “cứu dữ liệu” từ nguồn chưa tin cậy. Bật cấu hình yếu đi làm mất mục tiêu bảo vệ.

Khi nhận `XMLStreamException`, lấy Location nếu có, ghi diagnostic an toàn và **fail closed**.

## 10. Kiểm soát tài nguyên ngoài DTD

### 10.1. Giới hạn bytes trước parser

XMLReader dạng streaming **không tự** giới hạn số bytes của request. Với upload, đặt hard byte limit ở ingress layer hoặc wrapper của `InputStream` trước khi tạo reader. Nếu input nén, cần giới hạn **cả dữ liệu nén và dữ liệu sau giải nén**. Không chỉ tin header `Content-Length` do client cung cấp.

### 10.2. Giới hạn độ sâu

Trong cursor loop:

```java
if (event == XMLStreamConstants.START_ELEMENT) {
    depth++;
    if (depth > MAX_DEPTH) {
        throw new XMLStreamException(
                "Maximum XML depth exceeded",
                reader.getLocation());
    }
} else if (event == XMLStreamConstants.END_ELEMENT) {
    depth--;
}
```

Ví dụ này cần `depth/MAX_DEPTH/reader` được định nghĩa trong method. Dùng nó để tránh input với cây lồng quá sâu.

### 10.3. Giới hạn số events

Một XML có thể có rất nhiều thẻ ngắn dù tổng text nhỏ. Đếm events sau mỗi `next()` và từ chối nếu vượt budget. Count **không thay thế** bytes limit; nó chỉ bảo vệ phần xử lý từng event ở tầng ứng dụng.

### 10.4. Giới hạn text/attributes

`XMLStreamReader.getText()` có thể tạo hoặc trả text chunk lớn. Kiểm tra tổng chars được xử lý; với input byte stream lớn, byte budget ở tầng trước vẫn cần để tránh cấp phát quá sớm.

Đặc biệt, attributes và tag names có thể rất lớn; cần tài liệu limits của provider/JDK và request bounds. Các JDK có JAXP processing limit properties, nhưng không nên suy cấu hình của mọi third-party provider từ setting JDK-specific.

### 10.5. Giới hạn thời gian và concurrency

Parser có thể chờ Reader/InputStream từ mạng. Cấu hình network read timeout/HTTP request deadline ở tầng kết nối và tránh vô hạn retries. Các tài liệu nhỏ nhưng rất nhiều request đồng thời cũng có thể làm tăng RAM/CPU.

**Không** tuyên bố rằng tắt DTD làm parser hoàn toàn miễn nhiễm XML DoS. Đây chỉ là một lớp phòng thủ thiết yếu.

## 11. Chương trình Java 17+ hoàn chỉnh: `StaxDtdGuardDemo.java`

### 11.1. Mô hình

Đây là chương trình **StAX thật**, không mock XML parser. Nó có:

- `Guard.factory()` tạo `XMLInputFactory.newDefaultFactory()` đã cấu hình.
- `XMLStreamReader` đọc XML hợp lệ, tiền xử lý các sự kiện và áp budget.
- `XMLEventReader` đọc các events từ **cùng security configuration**.
- `XMLResolver` đếm callback và ném nếu có yêu cầu resource ngoài.
- `SUPPORT_DTD=false`, `IS_SUPPORTING_EXTERNAL_ENTITIES=false`, `ACCESS_EXTERNAL_DTD=""`.
- Test `&amp;`/Unicode, CDATA, DTD nội bộ, external entity, external DTD, comment chứa literal DOCTYPE, malformed XML.
- Test giới hạn depth/events/text với payload nhỏ, không dùng XML bomb thực.
- Test `XMLStreamException` mang Location khi budget bị vượt và nguồn input vẫn do caller sở hữu.

Các test cases cố ý không sử dụng file bí mật có thật và không gửi request ra ngoài. URL `example.invalid` là một tên minh họa, còn đường dẫn `file:///not-a-real-secret` không trỏ vào file mà chương trình cần đọc.

### 11.2. Mã nguồn đầy đủ

Lưu thành **`StaxDtdGuardDemo.java`**:

```java
import java.io.Reader;
import java.io.StringReader;
import java.util.concurrent.atomic.AtomicInteger;
import javax.xml.XMLConstants;
import javax.xml.stream.Location;
import javax.xml.stream.XMLInputFactory;
import javax.xml.stream.XMLEventReader;
import javax.xml.stream.XMLStreamConstants;
import javax.xml.stream.XMLStreamException;
import javax.xml.stream.XMLStreamReader;
import javax.xml.stream.events.XMLEvent;

public final class StaxDtdGuardDemo {
    static int passed;

    static void check(String label, boolean ok) {
        if (!ok) throw new AssertionError("FAIL " + label);
        System.out.println("PASS " + label);
        passed++;
    }

    record Limits(int depth, int events, int chars) {}

    record Summary(int starts, int ends, int events,
                   int deepest, String text) {}

    static final Limits BUDGET = new Limits(4, 60, 120);

    static final class TrackReader extends StringReader {
        boolean closed;

        TrackReader(String value) {
            super(value);
        }

        @Override
        public void close() {
            super.close();
            closed = true;
        }
    }

    static final class Guard {
        final AtomicInteger resolverCalls = new AtomicInteger();

        XMLInputFactory factory() {
            XMLInputFactory f = XMLInputFactory.newDefaultFactory();

            f.setProperty(
                    XMLInputFactory.IS_NAMESPACE_AWARE, true);
            f.setProperty(
                    XMLInputFactory.SUPPORT_DTD, false);
            f.setProperty(
                    XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES,
                    false);
            f.setProperty(
                    XMLConstants.ACCESS_EXTERNAL_DTD, "");

            f.setXMLResolver(
                    (publicId, systemId, baseUri, namespace) -> {
                        resolverCalls.incrementAndGet();
                        throw new XMLStreamException(
                                "External access is forbidden");
                    });

            return f;
        }
    }

    static Summary cursor(
            XMLInputFactory f,
            Reader source,
            Limits lim) throws XMLStreamException {

        XMLStreamReader r = f.createXMLStreamReader(source);
        XMLStreamException primary = null;

        try {
            int events = 0;
            int starts = 0;
            int ends = 0;
            int depth = 0;
            int deepest = 0;
            int chars = 0;

            StringBuilder collected = new StringBuilder();

            while (r.hasNext()) {
                int event = r.next();

                if (++events > lim.events()) {
                    throw new XMLStreamException(
                            "Event limit",
                            r.getLocation());
                }
                if (event == XMLStreamConstants.DTD) {
                    throw new XMLStreamException(
                            "DTD forbidden",
                            r.getLocation());
                }
                if (event == XMLStreamConstants.ENTITY_REFERENCE) {
                    throw new XMLStreamException(
                            "Entity forbidden",
                            r.getLocation());
                }

                if (event == XMLStreamConstants.START_ELEMENT) {
                    starts++;
                    deepest = Math.max(deepest, ++depth);

                    if (depth > lim.depth()) {
                        throw new XMLStreamException(
                                "Depth limit",
                                r.getLocation());
                    }
                } else if (event == XMLStreamConstants.END_ELEMENT) {
                    depth--;
                    ends++;
                } else if (event == XMLStreamConstants.CHARACTERS
                        || event == XMLStreamConstants.CDATA) {
                    String chunk = r.getText();
                    chars += chunk.length();

                    if (chars > lim.chars()) {
                        throw new XMLStreamException(
                                "Text limit",
                                r.getLocation());
                    }
                    collected.append(chunk);
                }
            }

            return new Summary(starts, ends, events,
                    deepest, collected.toString());

        } catch (XMLStreamException e) {
            primary = e;
            throw e;
        } finally {
            try {
                r.close();
            } catch (XMLStreamException closeError) {
                if (primary == null) throw closeError;
                primary.addSuppressed(closeError);
            }
        }
    }

    static int eventStarts(
            XMLInputFactory f,
            Reader source,
            Limits lim) throws XMLStreamException {

        XMLEventReader r = f.createXMLEventReader(source);
        XMLStreamException primary = null;

        try {
            int events = 0;
            int starts = 0;

            while (r.hasNext()) {
                XMLEvent event = r.nextEvent();

                if (++events > lim.events()) {
                    throw new XMLStreamException(
                            "Event limit",
                            event.getLocation());
                }
                if (event.getEventType() == XMLStreamConstants.DTD) {
                    throw new XMLStreamException(
                            "DTD forbidden",
                            event.getLocation());
                }
                if (event.isEntityReference()) {
                    throw new XMLStreamException(
                            "Entity forbidden",
                            event.getLocation());
                }
                if (event.isStartElement()) starts++;
            }

            return starts;

        } catch (XMLStreamException e) {
            primary = e;
            throw e;
        } finally {
            try {
                r.close();
            } catch (XMLStreamException closeError) {
                if (primary == null) throw closeError;
                primary.addSuppressed(closeError);
            }
        }
    }

    @FunctionalInterface
    interface XmlTask {
        void run() throws XMLStreamException;
    }

    static XMLStreamException expectFailure(XmlTask run) {
        try {
            run.run();
        } catch (XMLStreamException expected) {
            return expected;
        }
        throw new AssertionError(
                "Expected a parsing failure");
    }

    public static void main(String[] args) throws Exception {
        Guard guard = new Guard();
        XMLInputFactory f = guard.factory();

        check("dtd-support-disabled",
                Boolean.FALSE.equals(f.getProperty(
                        XMLInputFactory.SUPPORT_DTD)));
        check("external-entities-disabled",
                Boolean.FALSE.equals(f.getProperty(
                        XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES)));
        check("external-dtd-protocols-denied",
                "".equals(f.getProperty(
                        XMLConstants.ACCESS_EXTERNAL_DTD)));
        check("namespace-aware",
                Boolean.TRUE.equals(f.getProperty(
                        XMLInputFactory.IS_NAMESPACE_AWARE)));
        check("deny-resolver-installed",
                f.getXMLResolver() != null);

        String ok = "<root><name>Xin chào &amp; Java 🌿</name>"
                + "<safe><![CDATA[<x>]]></safe></root>";

        TrackReader input = new TrackReader(ok);
        Summary parsed = cursor(f, input, BUDGET);

        check("valid-xml-start-elements",
                parsed.starts() == 3);
        check("valid-xml-end-elements",
                parsed.ends() == 3);
        check("valid-xml-depth",
                parsed.deepest() == 2);
        check("built-in-ampersand-resolves",
                parsed.text().contains(
                        "Xin chào & Java 🌿"));
        check("cdata-kept-as-text",
                parsed.text().contains("<x>"));
        check("valid-document-no-resolver-call",
                guard.resolverCalls.get() == 0);

        // Input source belongs to caller, not the StAX parser.
        input.close();
        check("caller-closes-source",
                input.closed);

        check("event-reader-valid-document",
                eventStarts(f, new StringReader(ok),
                        BUDGET) == 3);

        String external =
                "<!DOCTYPE root [<!ENTITY ext SYSTEM "
                + "'file:///not-a-real-secret'>]>"
                + "<root>&ext;</root>";

        XMLStreamException externalError = expectFailure(
                () -> cursor(f,
                        new StringReader(external), BUDGET));
        check("external-entity-declaration-rejected",
                externalError != null);
        check("external-rejection-has-location",
                externalError.getLocation() != null);

        check("external-event-reader-rejects-dtd",
                expectFailure(() -> eventStarts(f,
                        new StringReader(external), BUDGET)) != null);
        check("external-resolver-not-entered",
                guard.resolverCalls.get() == 0);

        String internal =
                "<!DOCTYPE root [<!ENTITY item 'text'>]>"
                + "<root>&item;</root>";

        check("internal-dtd-declaration-rejected",
                expectFailure(() -> cursor(f,
                        new StringReader(internal), BUDGET)) != null);

        String externalSubset =
                "<!DOCTYPE root SYSTEM "
                + "'https://example.invalid/not-fetched.dtd'>"
                + "<root/>";

        check("external-subset-rejected",
                expectFailure(() -> cursor(f,
                        new StringReader(externalSubset),
                        BUDGET)) != null);
        check("still-no-resolver-use",
                guard.resolverCalls.get() == 0);

        String comment =
                "<root><!-- <!DOCTYPE root> -->"
                + "<item>ok</item></root>";

        check("comment-containing-doctype-is-safe",
                cursor(f, new StringReader(comment),
                        BUDGET).starts() == 2);

        String malformed = "<root><child></root>";
        check("bad-xml-still-fails",
                expectFailure(() -> cursor(f,
                        new StringReader(malformed),
                        BUDGET)) != null);

        String nested =
                "<a><b><c><d><e/></d></c></b></a>";
        XMLStreamException depth = expectFailure(
                () -> cursor(f,
                        new StringReader(nested), BUDGET));
        check("depth-budget-protects",
                depth.getMessage().contains("Depth limit"));

        String manyElements =
                "<root>" + "<item/>".repeat(50) + "</root>";
        XMLStreamException count = expectFailure(
                () -> cursor(f,
                        new StringReader(manyElements),
                        BUDGET));
        check("event-budget-protects",
                count.getMessage().contains("Event limit"));

        String bigText =
                "<root>" + "x".repeat(140) + "</root>";
        XMLStreamException text = expectFailure(
                () -> cursor(f,
                        new StringReader(bigText), BUDGET));
        check("text-budget-protects",
                text.getMessage().contains("Text limit"));

        check("budget-failures-retain-location",
                depth.getLocation() != null
                && count.getLocation() != null
                && text.getLocation() != null);

        check("events-outnumber-start-elements",
                parsed.events() > parsed.starts());
        check("factory-implementation-available",
                !f.getClass().getName().isBlank());
        check("no-external-resolver-calls-throughout",
                guard.resolverCalls.get() == 0);

        System.out.println("passed=" + passed);
    }
}
```

### 11.3. Biên dịch và chạy

Trong thư mục chứa `StaxDtdGuardDemo.java`:

```bash
javac --release 17 -encoding UTF-8 StaxDtdGuardDemo.java
java StaxDtdGuardDemo
```

Lệnh sau cũng đã được kiểm thử thành công với OpenJDK 24:

```bash
java -Djdk.xml.dtd.support=deny StaxDtdGuardDemo
```

**Lưu ý:** Nếu runtime Java 17, đừng suy rằng JDK-specific `jdk.xml.dtd.support` đã được hỗ trợ; code Java17 vẫn cần `SUPPORT_DTD=false`, external entity policy và kiểm thử provider. Các lệnh không cần thư viện ngoài, không mở file/URL chứa tài nguyên nhạy cảm.

### 11.4. Stdout thực tế đã xác minh

Cả hai chế độ chạy trên OpenJDK 24 đều in đúng các dòng sau (chỉ khác marker do người chạy thêm khi so sánh hai lệnh):

```text
PASS dtd-support-disabled
PASS external-entities-disabled
PASS external-dtd-protocols-denied
PASS namespace-aware
PASS deny-resolver-installed
PASS valid-xml-start-elements
PASS valid-xml-end-elements
PASS valid-xml-depth
PASS built-in-ampersand-resolves
PASS cdata-kept-as-text
PASS valid-document-no-resolver-call
PASS caller-closes-source
PASS event-reader-valid-document
PASS external-entity-declaration-rejected
PASS external-rejection-has-location
PASS external-event-reader-rejects-dtd
PASS external-resolver-not-entered
PASS internal-dtd-declaration-rejected
PASS external-subset-rejected
PASS still-no-resolver-use
PASS comment-containing-doctype-is-safe
PASS bad-xml-still-fails
PASS depth-budget-protects
PASS event-budget-protects
PASS text-budget-protects
PASS budget-failures-retain-location
PASS events-outnumber-start-elements
PASS factory-implementation-available
PASS no-external-resolver-calls-throughout
passed=29
```

**Kết quả QA:** `javac --release 17` trên JDK 24 PASS. Chạy bình thường **29/29 PASS**. Chạy cùng `-Djdk.xml.dtd.support=deny` **29/29 PASS**. Không cần database, không dùng XML bomb lớn, không cố truy cập tài nguyên ngoài thật.

### 11.5. Ý nghĩa kết quả

| Nhóm kiểm thử | Điều xác minh | Giới hạn của kết luận |
| --- | --- | --- |
| Factory properties | DTD và external entities tắt, external DTD protocols bị deny | Chỉ xác minh JDK provider đã chạy |
| Resolver | Resolver deny được cài đặt, không được gọi trong mẫu XML | Không chứng minh mọi provider có cùng internal resolution behavior |
| XML bình thường | Đọc được Unicode, `&amp;`, CDATA | Không có DTD nên không đánh đổi tính năng thiết yếu |
| XML có external entity | Tài liệu bị từ chối | Không mở file thật; test không đo network |
| Event API | Reader theo event cũng từ chối DTD | Không chỉ harden cursor path |
| Internal DTD | Entity nội bộ cũng bị từ chối theo policy | Không chạy expansion DoS |
| External subset | DOCTYPE SYSTEM URI bị từ chối | Không gửi HTTP request đến URI |
| Comment | Literal `<!DOCTYPE` trong comment không bị nhầm với declaration | Regex string scan không thể thay parser |
| Malformed XML | Vẫn ném `XMLStreamException` | Không bỏ qua well-formedness validation |
| Depth/events/text limits | Logic app dừng khi vượt budgets | Không thay byte limit và provider resource limits |
| Input ownership | Caller chủ động close Reader | Không phụ thuộc provider tự close tại EOF |

## 12. Một phát hiện thực tế về đóng Reader

Javadoc của `XMLStreamReader.close()` nói method này giải phóng resources của reader, **không có contract đóng underlying input source**. Vì vậy caller phải sở hữu/đóng `InputStream` hoặc `Reader` mà nó đã mở, ví dụ:

```java
try (InputStream in = Files.newInputStream(path)) {
    XMLStreamReader parser =
            secureFactory().createXMLStreamReader(in);
    try {
        // Parse bounded XML.
    } finally {
        parser.close();
    }
}
```

Đây là **snippet cần imports `java.io.InputStream`, `java.nio.file.Files/Path`**, method `secureFactory` và biến `path`. Mẫu này giữ ownership rõ ràng.

Một sắc thái triển khai: trong quá trình thử fixture với `StringReader`, JDK provider đã khiến reader nguồn được đóng khi parse tới cuối tài liệu. **Không được dựa vào quan sát này như một lời hứa portable rằng `parser.close()` luôn đóng input.** Vì thế code cuối cùng luôn cho caller gọi `input.close()` theo quyền sở hữu, dù một provider có thể đã chủ động đóng trước đó.

**Đừng** viết code xử lý XML an toàn nhưng quên đóng file/socket stream. Việc deny DTD không thay việc quản lý resources.

## 13. DTD không phải lớp duy nhất có thể tải tài nguyên ngoài

Một pipeline XML có thể gồm:

```text
Untrusted InputStream
       |
       v
Hardened StAX reader
       |
       +--> Business parsing / data extraction
       |
       +--> JAXB unmarshal (nếu được cung cấp reader đã harden)
       |
       +--> Schema validation (cần kiểm soát SchemaFactory/Validator riêng)
       |
       +--> XSLT transformation (cần kiểm soát TransformerFactory riêng)
```

Các lưu ý:

- **JAXB**: Nếu wrapper tự nhận raw InputStream rồi tự tạo parser, StAX factory settings của bạn có thể **không được áp dụng**. Hãy cung cấp hardened `XMLStreamReader`/`XMLEventReader` nếu API hỗ trợ, và kiểm thử wrapper.
- **SchemaFactory/Validator**: External schema loading có cài đặt `ACCESS_EXTERNAL_SCHEMA`, `ACCESS_EXTERNAL_DTD` và resolver riêng. Không coi `SUPPORT_DTD=false` trên StAX là đủ cho schema validation.
- **TransformerFactory**: XSLT có `xsl:include`, `xsl:import` và `document()`, cần `ACCESS_EXTERNAL_STYLESHEET`, `ACCESS_EXTERNAL_DTD` và `URIResolver` phù hợp. Một hardened StAX reader không tự kiểm soát network fetch do stylesheet.
- **DOM/SAX**: Có các factory/features riêng. Không copy `XMLInputFactory.SUPPORT_DTD` sang DOM parser rồi nghĩ API giống nhau.
- **XInclude**: Một số XML processors khác có thể nạp tài nguyên ngoài qua XInclude; StAX settings không phải security sandbox chung cho mọi bước.

Bài này chỉ dạy **StAX**; không dùng một cấu hình để khẳng định toàn bộ XML stack đã an toàn.

## 14. Nếu nghiệp vụ bắt buộc cần DTD thì sao?

Trong nhiều ứng dụng, câu trả lời tốt nhất vẫn là **không cần DTD**, dùng XML Schema hoặc một schema/bộ quy tắc ứng dụng do service kiểm soát. Nhưng nếu một định dạng XML đáng tin thực sự dùng DTD:

1. Xác định *vì sao* DTD cần thiết và đâu là trust boundary.
2. Phân biệt internal DTD có thể dùng với external subsets/parameter entities.
3. Không mở external protocols rộng rãi chỉ để tương thích một file.
4. Dùng **allowlisting resolver** hoặc XML Catalog với strict resolution tới những resources do hệ thống phê duyệt.
5. Giữ quyền truy cập network/file và resource budgets ở mức thấp nhất cần thiết.
6. Áp giới hạn entity expansion, entity size, total entity size, depth, memory và thời gian theo provider.
7. Kiểm thử với dữ liệu xấu và cấu hình production giống nhau.
8. Có versioned configuration và review bảo mật cho các exceptions policy.

**Không** khuyên chuyển `IS_SUPPORTING_EXTERNAL_ENTITIES=true` tùy tiện. Cấu hình có DTD là một trust-policy đặc biệt, không phải phương án mặc định cho XML bên ngoài.

### 14.1. Fail closed với unsupported properties

Nếu dùng provider không hỗ trợ setting:

```java
try {
    factory.setProperty(
            XMLInputFactory.SUPPORT_DTD, false);
    factory.setProperty(
            XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES, false);
} catch (IllegalArgumentException unsupported) {
    throw new IllegalStateException(
            "Cannot enforce required XML security settings",
            unsupported);
}
```

Đây là snippet trong method có `factory`. **Đừng** chỉ log warning rồi tiếp tục parse XML untrusted. Cũng đừng dùng `isPropertySupported` như “giấy chứng nhận an toàn”: cần test end-to-end bằng malformed/XXE-shaped inputs.

## 15. Test integration trên parser/provider của production

Fixture đã kiểm tra JDK default provider. Với production nên xây ma trận:

| Test | Dữ liệu | Kỳ vọng |
| --- | --- | --- |
| XML cơ bản | Elements/attributes/text | Parse thành công |
| Escape text | `&amp;`, `&lt;`, Unicode | Decode đúng |
| CDATA | `<![CDATA[...]]>` | Giữ nội dung như text |
| DOCTYPE trống | `<!DOCTYPE root>` | Từ chối nếu policy reject DOCTYPE |
| Internal DTD | Internal entity nhỏ | Không xử lý DTD nếu không được phép |
| External entity | SYSTEM file URI giả | Không đọc file, reject theo policy |
| External DTD | SYSTEM HTTP URI giả | Không gửi request, reject/deny access |
| Parameter entity | DTD có parameter entity | Không tải hoặc mở rộng |
| XML bomb shape | Payload nhỏ có khai báo lồng | Chặn sớm, không cần khai thác resource exhaustion thật |
| DOCTYPE in comment | Literal trong XML comment | Không nhầm thành declaration |
| Namespace | Prefix hợp lệ/không hợp lệ | Hành vi theo namespace-aware parser |
| Malformed XML | Sai thẻ đóng | Báo XMLStreamException |
| Deep nesting | Độ sâu vượt giới hạn | Dừng theo budget |
| Event count | Quá nhiều tags | Dừng theo budget |
| Long text | Text vượt chars budget | Dừng; vẫn có byte cap từ input layer |
| Unsupported property | Provider thiếu security setting | Fail closed |
| XMLEventReader | Event API riêng | Không bypass policy |
| Parser provider change | Chuyển JDK/third-party | Không regression chặn DTD/entity |
| Source ownership | File/HTTP stream | Source được caller đóng |
| Schema/XSLT integration | Transformer/validator | Có restrictions riêng |

Với test external access, dùng môi trường test đã cách ly mạng và file identifiers vô hại. Không kiểm thử XXE bằng cách cố đọc file mật hay thực hiện SSRF trên môi trường production.

**Điều quan trọng:** Nếu provider không phát sự kiện `DTD` khi `SUPPORT_DTD=false`, integration test phải xem policy thực tế: nó chỉ ignore hay thật sự reject? Nếu yêu cầu sản phẩm là strict reject, phải dùng cơ chế khác có bảo đảm theo runtime/provider, chẳng hạn JDK 22+ DTD deny property hoặc một parser validation layer rõ ràng.

## 16. Những sai lầm phổ biến

**1. Chỉ dùng `newFactory()` rồi parse XML không tin cậy.**  
Không đảm bảo defaults an toàn. Đặt explicit security controls.

**2. Chỉ đặt `SUPPORT_DTD=false` rồi nghĩ mọi external access bị loại bỏ ở mọi provider.**  
Đặt thêm `IS_SUPPORTING_EXTERNAL_ENTITIES=false`, deny external DTD protocols và resolver.

**3. Chỉ đặt `IS_SUPPORTING_EXTERNAL_ENTITIES=false` nhưng để DTD processing bật.**  
Internal DTD/entities vẫn có thể được xử lý. Khi không cần DTD, tắt DTD luôn.

**4. Nhầm bỏ qua DTD với từ chối DOCTYPE.**  
Một parser có thể tiếp tục đọc XML; strict reject cần cơ chế có bảo đảm.

**5. Tin rằng kiểm tra event `DTD` một mình luôn bắt được mọi DOCTYPE.**  
Provider có thể bỏ qua DTD mà không phát event.

**6. Dùng regex `contains("<!DOCTYPE")` làm security filter.**  
Sẽ sai với comments/CDATA/encodings; dùng parser policy đúng.

**7. Dùng `IS_REPLACING_ENTITY_REFERENCES=false` như biện pháp chặn XXE duy nhất.**  
Không. Nó kiểm soát event representation, không thay disable external resolution.

**8. Dùng `XMLConstants.FEATURE_SECURE_PROCESSING` như property chung trên StAX factory.**  
StAX không có hợp đồng này như DOM/SAX/Transformer; dùng StAX settings được hỗ trợ.

**9. Return null từ XMLResolver với ý định deny.**  
Có thể trả quyền giải tham chiếu về parser default. Deny bằng exception.

**10. Đặt settings sau khi đã tạo XMLStreamReader.**  
Không có bảo đảm reader cũ nhận cấu hình mới.

**11. Catch `IllegalArgumentException` do unsupported setting rồi vẫn parse.**  
Fail open nguy hiểm. Thất bại cấu hình phải ngăn nhận untrusted XML.

**12. Cho rằng `ACCESS_EXTERNAL_DTD=""` thay thế mọi protections khác.**  
External access property là một lớp, không thay DTD disable, resolver hay limits.

**13. Bật `http`, `https`, `file` vì một DTD duy nhất cần tải.**  
Protocol allowlist không phải per-host/per-file allowlist. Dùng catalog/resolver có kiểm soát.

**14. Giả định `jdk.xml.dtd.support=deny` có trên Java 17.**  
Đây là JDK-specific mechanism xuất hiện trong JDK 22+; version-target matters.

**15. Tin rằng StAX đã an toàn nên TransformerFactory cũng an toàn.**  
XSLT có external dependencies riêng, cần harden pipeline.

**16. Tin rằng XMLEventReader dùng default policy khác và không cần cấu hình.**  
Reader nào cũng phải được tạo từ factory đã harden.

**17. Không quản lý InputStream/Reader ownership.**  
Parser.close không có nghĩa caller được quên nguồn vào.

**18. Tin rằng parser.close luôn hoặc không bao giờ đóng source ở mọi provider/runtime.**  
Contract và implementation có thể khác trong thực tế. Caller nên quản lý source scope rõ.

**19. Chạy payload XML bomb khổng lồ trên production để “test”.**  
Không cần. Kiểm thử rejection sớm bằng mẫu nhỏ.

**20. Không giới hạn độ sâu và số events.**  
XML không có DTD vẫn có thể gây DoS.

**21. Không giới hạn số bytes đầu vào và dữ liệu sau giải nén.**  
Event budgets không thay thế hard ingress byte bounds.

**22. Tự mở URL do user cung cấp rồi nghĩ XMLResolver sẽ chặn.**  
Initial URL opening xảy ra bên ngoài parser.

**23. Log nguyên XML hoặc systemId chứa secrets khi bắt lỗi.**  
Chỉ log dữ liệu tối thiểu cần thiết, có redact.

**24. Chỉ test valid XML, không test external entity và internal DTD.**  
Không đủ để chứng minh security controls hoạt động.

**25. Coi callback resolver không được gọi là bảo đảm an toàn tuyệt đối.**  
Phải kết hợp settings, chính sách network/file, test provider và resource bounds.

**26. Dùng raw source `String` để xử lý tài liệu nhiều GB.**  
StAX có thể stream, nhưng bạn đã materialize cả input trước khi parser đọc. Dùng bounded streams theo thiết kế.

**27. Không kiểm soát provider lookup khi có third-party parser.**  
`newFactory()` có thể chọn provider khác, cần kiểm thử tương thích và security settings.

**28. Dùng cùng mutable factory và thay đổi properties giữa các requests đồng thời.**  
Không có bảo đảm cấu hình thay đổi trong lúc tạo readers là an toàn. Tạo/configure ở startup, quản lý lifecycle.

## 17. Checklist áp dụng

- [ ] Xác định nguồn XML có thể không tin cậy.
- [ ] Khẳng định nghiệp vụ **không cần DTD**, hoặc có chính sách riêng nếu cần.
- [ ] Set `XMLInputFactory.SUPPORT_DTD=false` **trước khi tạo reader**.
- [ ] Set `IS_SUPPORTING_EXTERNAL_ENTITIES=false`.
- [ ] Hạn chế external DTD access bằng property phù hợp với provider.
- [ ] Cài `XMLResolver` deny-all nếu không cần external references.
- [ ] Không bỏ qua lỗi unsupported security configuration.
- [ ] Nếu phải reject DOCTYPE, chọn cơ chế có bảo đảm; cân nhắc JDK 22+ `jdk.xml.dtd.support=deny`.
- [ ] Kiểm tra DTD events bổ sung, nhưng không tin event check là universal reject.
- [ ] Áp cấu hình với cả cursor và event reader paths.
- [ ] Dùng giới hạn bytes/depth/event count/text/time.
- [ ] InputStream/Reader được sở hữu và đóng rõ ràng.
- [ ] Xử lý XMLStreamException có Location an toàn; không hiển thị secrets.
- [ ] Hệ thống downstream (JAXB/schema/XSLT) có cấu hình riêng.
- [ ] Test external/internal DTD/entity, malformed XML, predefined entities và CDATA.
- [ ] Thử trên đúng JDK và provider sẽ chạy production.
- [ ] Giám sát XML parsing failures/security violations và memory/CPU usage.

## 18. Câu hỏi ôn tập

**1. Khi không cần DTD, nên đặt property nào đầu tiên?**  
`XMLInputFactory.SUPPORT_DTD=false`.

**2. Tại sao còn đặt `IS_SUPPORTING_EXTERNAL_ENTITIES=false`?**  
Để tắt khả năng phân giải external parsed entities.

**3. `SUPPORT_DTD=false` có chắc chắn từ chối mọi tài liệu chứa DOCTYPE?**  
Không. Một provider có thể ignore DTD và parse tiếp.

**4. Khi cần strict DOCTYPE rejection trên JDK 22+, có property gì?**  
`jdk.xml.dtd.support=deny` theo JAXP Security Guide.

**5. Property này có thể được code target Java 17 tin dùng trên Java 17 không?**  
Không nên: đây là JDK-specific mechanism của JDK mới hơn, không phải contract Java 17.

**6. Vì sao dùng resolver ném `XMLStreamException` thay vì return null?**  
Vì null có thể để parser tiếp tục dùng default resolver.

**7. `ACCESS_EXTERNAL_DTD=""` có ý nghĩa gì?**  
Từ chối các external DTD access protocols trên provider hỗ trợ property.

**8. Vì sao `&amp;` vẫn phải parse được?**  
Đó là predefined XML entity, không cần user-defined DTD.

**9. CDATA có phải DTD không?**  
Không. CDATA biểu diễn text literal.

**10. Vì sao regex tìm `<!DOCTYPE` có thể sai?**  
Vì chuỗi đó có thể là text trong comment hoặc CDATA và còn các vấn đề lexical/encoding.

**11. Tắt DTD có ngăn toàn bộ DoS từ XML không?**  
Không. Vẫn cần giới hạn input bytes, depth, events, text và thời gian.

**12. `XMLStreamReader.close()` có thay thế việc đóng InputStream/Reader của caller không?**  
Không được dựa vào điều đó. Quản lý ownership riêng cho nguồn.

**13. Nếu provider không hỗ trợ security setting, nên làm gì?**  
Fail closed và không xử lý untrusted XML.

**14. Nếu XML được đưa qua JAXB hoặc XSLT thì sao?**  
Phải bảo đảm wrapper nhận hardened parser và harden riêng transformation/validation layers.

**15. Có thể dựa vào `getXMLResolver() != null` để kết luận an toàn?**  
Không. Cần policy đúng, behavior tests và resource bounds.

**16. Vì sao cả XMLStreamReader và XMLEventReader phải được thử?**  
Vì ứng dụng có thể sử dụng một trong hai API; không muốn đường event bypass security settings.

**17. 29/29 PASS có chứng minh mọi provider khác cũng an toàn?**  
Không. Đó là kết quả với JDK provider và các inputs đã test; cần production-specific tests.

## 19. Tài liệu hiện hành

- [Java SE 26 — `XMLInputFactory`](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/XMLInputFactory.html): bảng properties chuẩn, default behavior, `SUPPORT_DTD`, `IS_SUPPORTING_EXTERNAL_ENTITIES` và factory methods.
- [Java SE 26 — `XMLResolver`](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/XMLResolver.html): giao diện giải quyết external resources.
- [Java SE 26 — `XMLStreamReader`](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/XMLStreamReader.html): cursor events, `next()`, `getLocation()`, `close()`.
- [Java SE 26 — `XMLEventReader`](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/XMLEventReader.html): event API và cleanup.
- [Java SE 26 — `XMLStreamConstants`](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/XMLStreamConstants.html): `DTD`, `ENTITY_REFERENCE`, `START_ELEMENT` và các event codes.
- [Java SE 26 — `XMLStreamException`](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/XMLStreamException.html): thông báo lỗi, Location và nguyên nhân.
- [Java SE 26 — `XMLConstants`](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/XMLConstants.html): external-access properties.
- [Oracle Java SE 26 — JAXP Security Guide](https://docs.oracle.com/en/java/javase/26/security/java-api-xml-processing-jaxp-security-guide.html): DTD policy `allow/ignore/deny`, giới hạn external resources và bảo vệ XML processor.
- [OWASP — XML External Entity Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/XML_External_Entity_Prevention_Cheat_Sheet.html): cấu hình StAX hiện hành, disable DTD/external entities, resolver deny và fail-closed guidance.

**Kết luận:** Với XML không tin cậy và nghiệp vụ không cần DTD, hãy **tắt cả DTD processing và external entity resolution**, hạn chế external DTD access, dùng resolver từ chối external references và fail closed nếu cấu hình không được hỗ trợ. Phân biệt **ignore DTD** với **reject DOCTYPE**; khi cần reject nghiêm ngặt, áp dụng cơ chế có bảo đảm trên đúng JDK/provider. Đồng thời giới hạn bytes, độ sâu, số events, text và thời gian, kiểm thử cả cursor/event paths và giữ ownership nguồn đầu vào rõ ràng.
