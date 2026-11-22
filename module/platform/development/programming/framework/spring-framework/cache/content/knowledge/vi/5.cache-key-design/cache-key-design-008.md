# Khóa bất biến, biểu diễn ổn định và giới hạn kích thước trong Spring Cache

## 1. Vì sao thiết kế cache key là một quyết định kiến trúc?

Trong Spring Cache, `@Cacheable` xác định cách Spring tìm kết quả đã lưu cho một lời gọi phương thức. Mỗi thao tác thường gắn với cặp **(tên cache, key)**: cùng tên cache và key tương đương thì có thể đọc lại cùng một entry. Nếu key không phân biệt đủ ngữ cảnh, hệ thống có thể trả **sai dữ liệu**; nếu key thay đổi vô cớ, cache luôn miss; nếu key quá lớn hoặc có vô số biến thể, bộ nhớ và băng thông bị lãng phí.

Ba phẩm chất cần có của một khóa tốt:

1. **Bất biến (immutable):** sau khi được tính và đưa vào cache, danh tính logic của khóa không tự thay đổi. Các thành phần dùng trong `equals()`/`hashCode()` hoặc giá trị đã serialize phải được chốt.
2. **Biểu diễn ổn định (stable representation):** cùng một yêu cầu logic luôn tạo đúng một key theo một quy ước xác định; các yêu cầu khác nhau có ảnh hưởng đến kết quả không bị gộp chung. Quy ước phải nhất quán giữa phương thức đọc, ghi, xóa, giữa các service instance và qua các bản triển khai dự kiến cùng chia sẻ cache.
3. **Kích thước có giới hạn (bounded size):** key có độ dài có thể dự đoán, đo bằng byte của biểu diễn thực tế (thường là UTF-8), và không cho phép dữ liệu đầu vào tùy ý làm key nở không giới hạn.

Ví dụ `findProduct(tenantId, productId, locale)` trả mô tả theo ngôn ngữ và tenant. Nếu chỉ dùng `productId`, một sản phẩm có thể lấy nhầm kết quả của tenant hoặc ngôn ngữ khác. Nếu nhét toàn bộ HTTP request thành key, một header vô thưởng vô phạt cũng có thể tạo entry mới.

Thiết kế key là bài toán **định danh kết quả hàm**, chứ không chỉ là biến đổi tham số thành một chuỗi. Một key hợp lệ thỏa bất biến:

> Nếu hai lời gọi có thể cho **kết quả khác nhau** trong cùng khoảng hiệu lực của cache, key của chúng phải phân biệt được; nếu chúng được coi là tương đương theo nghiệp vụ, việc chuẩn hóa nên tạo cùng một key.

Quy tắc này phải đi cùng chính sách TTL, invalidation, phân quyền dữ liệu và versioning. Key tốt không tự bảo đảm dữ liệu mới nhất.

## 2. Spring tạo key mặc định như thế nào?

Spring Cache dùng `org.springframework.cache.interceptor.KeyGenerator`. Khi không có `key` (SpEL) hay `keyGenerator` riêng, `SimpleKeyGenerator` mặc định hoạt động theo cách khái quát sau:

| Số tham số | Key mặc định | Điều cần lưu ý |
| --- | --- | --- |
| 0 | `SimpleKey.EMPTY` | Nếu nhiều method cùng dùng **một tên cache** và không có tham số, các method có nguy cơ dùng cùng key. |
| 1 | Chính argument duy nhất nếu phù hợp, hoặc `SimpleKey` cho trường hợp đặc biệt như null/array | Phụ thuộc ngữ nghĩa `equals()/hashCode()` của argument; không tự nhận biết tenant ẩn, phiên bản API hoặc các giá trị bên ngoài. |
| Từ 2 | `SimpleKey` chứa các arguments theo thứ tự | So sánh tổ hợp argument; vẫn có rủi ro nếu một argument có trạng thái biến đổi. |

`SimpleKey` của Spring không đơn thuần lấy mã `hashCode()` 32-bit làm danh tính cuối cùng; với local cache nó thực hiện so sánh theo các phần tử. Tuy vậy, Javadoc cũng cảnh báo đối tượng `SimpleKey` có thể không phù hợp với **mọi cache backend**. Đừng mặc định key object của Java sẽ được Redis, Memcached, Caffeine và các serializer diễn giải giống nhau.

**Ranh giới dễ nhầm:** `SimpleKeyGenerator` không tự thêm tên method, target class, tenant, ngôn ngữ, quyền truy cập hay bản phát hành vào *giá trị key*. Spring dùng tên cache để xác định vùng lưu; nếu hai method ghi vào cùng một vùng với key giống nhau, chúng có thể va chạm về mặt logic. Đặt tên cache khác hoặc thêm một danh tính operation rõ ràng khi cần chia sẻ cùng vùng.

Ví dụ sau là các **khai báo Spring minh họa**, cần đặt trong Spring bean và có method body thực tế:

~~~java
@Cacheable(cacheNames = "products", key = "#p0")
public Product findById(String productId) {
    // ...
}

@Cacheable(cacheNames = "productViews", key = "#p0 + ':' + #p1")
public ProductView findLocalized(String productId, String locale) {
    // ...
}
~~~

Cách nối chuỗi ở ví dụ thứ hai dễ hiểu nhưng chỉ an toàn nếu dấu phân cách không thể gây nhập nhằng, các trường được chuẩn hóa và đầu vào đã bị giới hạn. Với nhiều trường hoặc giá trị tự do, hãy dùng cấu trúc định danh có độ dài từng trường hoặc bộ mã hóa chuẩn hóa riêng.

## 3. Khóa bất biến: điều kiện để tra cứu chính xác

### 3.1. Vì sao key thay đổi sau khi put lại nguy hiểm?

Một `HashMap`/`ConcurrentHashMap` dùng hash và equality tại thời điểm chèn/tra cứu. Nếu thuộc tính tham gia `hashCode()` của object key đổi sau khi put, lookup có thể không tìm lại được entry mặc dù object đó vẫn còn trong map.

Minh họa lỗi:

~~~java
final class MutableProductKey {
    String tenantId;
    String productId;

    MutableProductKey(String tenantId, String productId) {
        this.tenantId = tenantId;
        this.productId = productId;
    }

    @Override
    public boolean equals(Object other) {
        if (!(other instanceof MutableProductKey k)) return false;
        return java.util.Objects.equals(tenantId, k.tenantId)
                && java.util.Objects.equals(productId, k.productId);
    }

    @Override
    public int hashCode() {
        return java.util.Objects.hash(tenantId, productId);
    }
}
~~~

Đây là **class minh họa** (chưa có `main`). Nếu đưa instance vào cache/mapping rồi sửa `productId`, giá trị hash không còn ổn định. Vấn đề không chỉ là miss: entry cũ có thể tồn tại cho tới khi bị eviction, khiến cache phình và làm invalidation khó dự đoán. Việc đổi field của object được cache làm **value** là một vấn đề khác; bài này tập trung vào danh tính **key**.

### 3.2. Dùng record, final field và snapshot đúng cách

Java 17 `record` phù hợp với các key chứa giá trị bất biến như `String`, `int`, `UUID` hay `Instant`. Record tự sinh `equals()/hashCode()` theo các component và hạn chế thay đổi tham chiếu field. Nhưng record chỉ bất biến ở **mức tham chiếu**, không tự đóng băng object bên trong:

~~~java
record BadKey(String tenant, java.util.List<String> filters) {}

var filters = new java.util.ArrayList<String>();
filters.add("active");
var key = new BadKey("tenant-a", filters);
filters.add("draft");  // key.filters() cũng thay đổi
~~~

Đoạn trên chỉ để chỉ ra lỗi shallow immutability; là ví dụ cắt từ một method, không phải file độc lập. Dùng `List.copyOf(filters)` trong constructor để chụp snapshot. Với `List<MutableFilter>`, bản sao danh sách vẫn chứa element có thể đổi: cần chuyển từng element thành một giá trị bất biến hoặc tự deep-copy.

Nguyên tắc thực hành:

- Đóng băng **toàn bộ trường xác định danh tính** trước khi gọi cache; tránh chuyển trực tiếp entity JPA đang mutate, request builder, `Date` hoặc `List` có thể bị sửa.
- `String`, primitive wrapper, `UUID` và immutable value object là lựa chọn dễ kiểm soát. Với array, phải copy dữ liệu và dùng content equality phù hợp, đừng dựa vào `Object.equals()` mặc định cho array.
- Không đưa biến đổi theo thời điểm như `System.currentTimeMillis()`, random UUID mỗi lần, session token mới hay dấu thời gian request vào key trừ khi chúng thực sự là một phần của danh tính kết quả.
- Không lạm dụng `toString()` của object làm key: kiểu mặc định `Class@hash` có thể phụ thuộc identity; kiểu do IDE sinh có thể đổi khi refactor hoặc log lộ dữ liệu nhạy cảm.
- Nếu muốn dùng record trực tiếp với cache trong bộ nhớ, key phải có `equals()/hashCode()` bền vững. Khi cache phân tán, thiết kế thêm **wire format** ổn định để serializer ở các node dùng cùng một quy ước.

## 4. Biểu diễn ổn định và chuẩn hóa đầu vào

### 4.1. Quy định schema trước khi viết mã

Ví dụ một operation trả kết quả cho cặp tenant/sản phẩm/ngôn ngữ và một tập nhãn:

| Trường | Có tham gia key? | Quy tắc ví dụ |
| --- | --- | --- |
| Operation/version | Có | `catalog.query:v1`, cố định theo contract. |
| `tenantId` | Có | Giữ đúng danh tính tenant đã xác thực; không lấy tùy tiện từ dữ liệu caller không đáng tin. |
| `sku` | Có | Nếu SKU phân biệt hoa/thường, **không** tự lowercase. Chỉ strip khoảng trắng khi nghiệp vụ coi khoảng trắng ngoài vô nghĩa. |
| `locale` | Có | Chuẩn hóa theo mã ngôn ngữ BCP 47, ví dụ `vi-VN`. |
| `tags` | Có nếu ảnh hưởng kết quả | Sắp xếp và khử trùng **chỉ khi** tags là một *tập* không quan tâm thứ tự. |
| Trace ID, header chỉ phục vụ logging | Không | Nếu kết quả không phụ thuộc, đưa vào key chỉ làm giảm hit rate. |
| Quyền truy cập/phân vùng dữ liệu | Có nếu ảnh hưởng kết quả | Thường tách qua tenant hoặc một scope/version của authorization; không dùng thông tin nhạy cảm dạng thô. |

Hệ thống phải định nghĩa chính xác **khi nào hai yêu cầu tương đương**. Ví dụ `"SKU-A"` và `"sku-a"` chỉ có thể thành cùng key nếu miền nghiệp vụ coi chúng là một mã. Sắp xếp `tags` chỉ đúng khi thứ tự không ảnh hưởng việc tính kết quả. Quy tắc normalize sai có thể nguy hiểm hơn không normalize.

### 4.2. Các va chạm do mã hóa mơ hồ

Nối chuỗi không đủ định danh có thể gây trùng:

- `"ab" + "c"` và `"a" + "bc"` cùng thành `"abc"`.
- Ghép bằng dấu `":"` cũng có thể mơ hồ nếu một trường chứa `":"`, trừ khi escape đúng và có thuật toán giải mã duy nhất.
- `null`, chuỗi rỗng, chuỗi `"null"`, trường không có mặt và giá trị mặc định có thể là các trạng thái khác nhau về nghiệp vụ.
- Số `1`, `1.0` và `1.00`; ngày giờ cùng thời điểm nhưng khác timezone; Unicode ký tự tổ hợp và ký tự dựng sẵn; thứ tự entry trong `HashMap` có thể dẫn tới biểu diễn khác.

Những cách mã hóa có thể dùng:

1. **Value object bất biến** để dùng làm key trong local cache, với equality đúng nghiệp vụ.
2. **Định dạng có cấu trúc** với thứ tự field cố định và độ dài field rõ ràng. Ví dụ mã hóa mỗi chuỗi thành `4 byte chiều dài (big-endian) + UTF-8 bytes`. Phân biệt được mọi cặp giá trị ngay cả khi chứa dấu phân cách hoặc ký tự Unicode.
3. **JSON canonical** theo một đặc tả thống nhất, nếu toàn bộ node và ngôn ngữ hỗ trợ: thứ tự field, kiểu số, `null`, escape và Unicode phải cùng quy tắc. JSON do hai thư viện serialize theo mặc định không đương nhiên giống byte-for-byte.
4. **Digest của dữ liệu canonical** nếu muốn key có kích thước cố định: `namespace:version:hex(SHA-256(canonicalBytes))`. Cần chuẩn hóa trước rồi mới hash.

Không dùng `Object.hashCode()`, `Objects.hash(...)` hoặc `String.hashCode()` 32-bit làm **mã định danh phân tán duy nhất**. Chúng là hash phục vụ cấu trúc dữ liệu Java, không phải fingerprint chống trùng đủ mạnh cho một kho key rộng lớn. `equals()` vẫn cần để phân biệt hai key có hash trùng trong local map.

### 4.3. Schema phải có version

Ngay cả khi digest đã có độ dài cố định, thay đổi cách normalize hoặc thứ tự field sẽ thay đổi digest của cùng yêu cầu. Khai báo namespace/version như `catalog:query:v1:...` giúp phân biệt key trước và sau thay đổi thuật toán.

Khi triển khai rolling deployment nhiều phiên bản ứng dụng cùng dùng cache, cần xét các node đã nâng cấp và chưa nâng cấp. Không nên để v1 và v2 vô tình dùng cùng prefix nhưng diễn giải key khác nhau. Có thể cho version cũ hết TTL tự nhiên, chủ động clear vùng cache tương ứng hoặc dùng cache name mới; chọn cách dựa trên mục tiêu nhất quán và chi phí làm nóng lại cache.

## 5. Giới hạn kích thước: số byte quan trọng hơn số ký tự

Key được dùng trong lookup, truyền qua mạng, serialize, log/metrics và lưu metadata của provider. Dù backend có thể cho phép key rất dài, key hàng chục KB thường gây tốn bộ nhớ, băng thông, CPU so sánh và làm giảm hiệu quả cache.

**Không có một giới hạn ký tự chung của Spring Cache.** Hạn chế thực tế phụ thuộc `Cache` implementation, serializer và backend. Vì thế phải đặt ngân sách riêng cho hệ thống và đo **UTF-8 byte length** sau khi mã hóa:

~~~java
int byteCount = key.getBytes(java.nio.charset.StandardCharsets.UTF_8).length;
if (byteCount > 128) {
    throw new IllegalArgumentException("Cache key exceeds 128-byte policy");
}
~~~

Đây là **đoạn mã minh họa**, `key` là chuỗi đã được tạo từ trước. Mốc `128 byte` chỉ là **ngân sách ví dụ của ứng dụng**, không phải giới hạn bắt buộc của Spring hay Redis. Một ký tự tiếng Việt có thể chiếm nhiều byte UTF-8; đo bằng `String.length()` sẽ không phản ánh chính xác độ dài khi truyền/lưu.

Nếu key gồm namespace và hash SHA-256 biểu diễn hex thì kích thước cố định, ví dụ `catalog:query:v1:` (17 byte ASCII) + digest (64 byte ASCII) = **81 byte UTF-8**. Nếu dùng Base64URL không padding, hash SHA-256 thường có 43 ký tự ASCII, nhưng cần chọn một format thống nhất cho mọi node. Hãy cân nhắc cả overhead tên cache mà backend có thể tự thêm vào key vật lý.

**Hash chỉ giới hạn kích thước đầu ra.** Nó không tự giải quyết việc đọc/chuẩn hóa payload đầu vào khổng lồ: phải đặt giới hạn cho số trường, độ dài từng trường, độ dài tổng dữ liệu canonical và số tổ hợp key khác nhau (*cardinality*). Nếu mỗi request chứa chuỗi ngẫu nhiên, digest dù chỉ 64 ký tự vẫn tạo một entry mới liên tục.

### Đánh đổi raw key và hashed key

| Tiêu chí | Chuỗi có trường đọc được | Key dạng digest |
| --- | --- | --- |
| Debug thủ công | Dễ thấy tenant/id/filter nếu không bị ẩn | Cần công cụ tái tính fingerprint từ input chuẩn hóa |
| Độ dài | Tăng theo dữ liệu | Gần cố định |
| Độ nhạy dữ liệu | Dễ để lộ thông tin trong Redis monitor/log | Tránh lưu trực tiếp nội dung, nhưng hash **không phải mã hóa bí mật** |
| Nguy cơ va chạm | Phụ thuộc thiết kế escape/encoding | SHA-256 có xác suất va chạm cực thấp nhưng không tuyệt đối bằng 0 |
| Thay đổi schema | Phải version hóa | Cũng phải version hóa |
| Chi phí CPU | Serialize + truyền chuỗi | Serialize + tính digest; thường chấp nhận được nếu input có giới hạn |

Đừng lầm SHA-256 thuần với biện pháp bảo mật PII: đối với giá trị có không gian nhỏ (email phổ biến, số định danh có thể đoán), kẻ có khả năng quan sát key có thể thử từ điển. Khi cần hạn chế khả năng đoán key, cân nhắc **HMAC-SHA-256** với secret được quản lý an toàn, rotation có version rõ ràng và không ghi raw input vào log. HMAC không thay thế kiểm tra authorization.

## 6. Ví dụ Java 17+ chạy độc lập: snapshot, canonical encoding và key 81 byte

Chương trình này dùng **Java chuẩn, không cần Spring dependency** để kiểm thử phần lõi của thiết kế key. Sau đó có thể gọi `cacheKey(...)` từ Spring `KeyGenerator`. Đặt nguyên file tại `CacheKeyDemo.java`:

~~~java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.List;
import java.util.Locale;
import java.util.Objects;

public final class CacheKeyDemo {
    private static final int MAX_FIELD_BYTES = 2_048;
    private static final int MAX_CANONICAL_BYTES = 8_192;
    private static final int MAX_KEY_BYTES = 128;
    private static final String KEY_PREFIX = "catalog:query:v1:";

    private CacheKeyDemo() {}

    // Đây là danh tính logic của yêu cầu, đã chốt sau khi tạo.
    public record CatalogQuery(
            String tenantId, String sku, String locale, List<String> tags) {

        public CatalogQuery {
            tenantId = required(tenantId, "tenantId");
            sku = required(sku, "sku");

            String languageTag = required(locale, "locale");
            locale = Locale.forLanguageTag(languageTag).toLanguageTag();
            if ("und".equals(locale)) {
                throw new IllegalArgumentException("Invalid locale");
            }

            // Trong ví dụ, tags là TẬP: không quan tâm thứ tự và trùng lặp.
            tags = List.copyOf(
                    Objects.requireNonNull(tags, "tags")
                           .stream()
                           .map(tag -> required(tag, "tag"))
                           .distinct()
                           .sorted()
                           .toList()
            );
        }
    }

    private static String required(String value, String field) {
        Objects.requireNonNull(value, field);
        String clean = value.strip();
        if (clean.isEmpty()) {
            throw new IllegalArgumentException(field + " must not be blank");
        }
        return clean;
    }

    private static void writeText(DataOutputStream output, String value)
            throws IOException {
        byte[] utf8 = value.getBytes(StandardCharsets.UTF_8);
        if (utf8.length > MAX_FIELD_BYTES) {
            throw new IllegalArgumentException("Input field too large");
        }
        output.writeInt(utf8.length); // 4 byte big-endian
        output.write(utf8);
    }

    private static byte[] canonicalBytes(CatalogQuery q) {
        Objects.requireNonNull(q, "query");
        try {
            ByteArrayOutputStream buffer = new ByteArrayOutputStream();
            try (DataOutputStream output = new DataOutputStream(buffer)) {
                // Thứ tự và kiểu field là một phần của protocol.
                writeText(output, "catalog.query.v1");
                writeText(output, q.tenantId());
                writeText(output, q.sku());
                writeText(output, q.locale());
                output.writeInt(q.tags().size());
                for (String tag : q.tags()) {
                    writeText(output, tag);
                }
            }
            byte[] bytes = buffer.toByteArray();
            if (bytes.length > MAX_CANONICAL_BYTES) {
                throw new IllegalArgumentException("Canonical input too large");
            }
            return bytes;
        } catch (IOException e) {
            throw new IllegalStateException("Cannot encode cache key", e);
        }
    }

    private static byte[] sha256(byte[] value) {
        try {
            return MessageDigest.getInstance("SHA-256").digest(value);
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 unavailable", e);
        }
    }

    public static String cacheKey(CatalogQuery query) {
        String result = KEY_PREFIX
                + HexFormat.of().formatHex(sha256(canonicalBytes(query)));
        if (result.getBytes(StandardCharsets.UTF_8).length > MAX_KEY_BYTES) {
            throw new IllegalArgumentException("Cache key too long");
        }
        return result;
    }

    public static void main(String[] args) {
        var sourceTags = new ArrayList<>(List.of("sale", "new"));
        var first = new CatalogQuery(
                "tenant-A", "SKU-42", "vi-VN", sourceTags);
        String key1 = cacheKey(first);

        System.out.println("tags: " + first.tags());

        var same = new CatalogQuery(
                "tenant-A", "SKU-42", "vi-VN", List.of("new", "sale"));
        System.out.println("same logical key: "
                + key1.equals(cacheKey(same)));

        sourceTags.add("vip");
        System.out.println("stable after caller mutation: "
                + key1.equals(cacheKey(first)));

        var anotherTenant = new CatalogQuery(
                "tenant-B", "SKU-42", "vi-VN", List.of("new", "sale"));
        System.out.println("different tenant: "
                + !key1.equals(cacheKey(anotherTenant)));

        System.out.println("UTF-8 bytes: "
                + key1.getBytes(StandardCharsets.UTF_8).length);
    }
}
~~~

Biên dịch và chạy trong thư mục chứa file:

~~~bash
javac --release 17 -encoding UTF-8 CacheKeyDemo.java
java CacheKeyDemo
~~~

Output theo đúng thứ tự:

~~~text
tags: [new, sale]
same logical key: true
stable after caller mutation: true
different tenant: true
UTF-8 bytes: 81
~~~

**Vì sao ví dụ ổn định?**

- `CatalogQuery` nhận snapshot `List<String>` đã sắp xếp/khử trùng. Việc sửa `sourceTags` sau đó không đổi key đã tạo.
- Tenant, SKU, locale, tags và version được mã hóa theo thứ tự cố định. Mỗi chuỗi có chiều dài byte riêng nên không thể nhập nhằng bởi dấu phân cách.
- `DataOutputStream.writeInt` dùng big-endian; `String.getBytes(UTF_8)` tạo byte UTF-8. Đó là **contract mã hóa cụ thể** để có thể triển khai ở nhiều tiến trình/ngôn ngữ.
- SHA-256 chuyển danh tính canonical thành digest 32 byte, `HexFormat` tạo 64 ký tự hex và prefix tạo tổng 81 byte.
- Ví dụ giới hạn mỗi field 2.048 byte, canonical input 8.192 byte và key 128 byte. Các mốc đó cần điều chỉnh theo yêu cầu thực tế, không phải mặc định Spring.
- `strip()` và việc coi `tags` là tập là **quyết định nghiệp vụ của ví dụ**. Nếu khoảng trắng hay thứ tự tags mang ý nghĩa, phải đổi schema và bump version.

**Lưu ý về tính bất biến:** key cuối là `String` bất biến. `CatalogQuery` chỉ chứa `String` và danh sách immutable của `String`. Với nested objects có thể thay đổi, phải chuyển sang representation bất biến thực sự trước khi đưa vào record. Với các dữ liệu được thay đổi trong quá trình build request, phải snapshot sau khi đã áp dụng xong các bước chuẩn hóa.

## 7. Gắn quy tắc key vào Spring Cache

Có hai cách phổ biến:

- **SpEL `key`:** phù hợp vài trường đơn giản và có biểu diễn đã chuẩn hóa sẵn, ví dụ `key = "#p0.tenantId() + ':' + #p0.sku()"` nếu quy tắc delimiter thực sự an toàn trong miền dữ liệu đó.
- **`KeyGenerator` bean:** phù hợp schema có nhiều trường, canonical encoding, digest, kiểm soát byte length và quy ước dùng chung giữa các method.

Mẫu cấu hình dưới đây **minh họa cách tích hợp**, giả định ứng dụng đã có `CacheKeyDemo.CatalogQuery`/`CacheKeyDemo.cacheKey(...)` từ phần 6 và repository/domain model `CatalogView`. Cần chuyển class hỗ trợ sang package của ứng dụng khi triển khai Spring thực tế.

~~~java
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.cache.interceptor.KeyGenerator;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableCaching
class CacheConfiguration {
    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("catalogViews");
    }

    @Bean("catalogQueryKeyGenerator")
    KeyGenerator catalogQueryKeyGenerator() {
        return (target, method, params) -> {
            if (params.length != 1
                    || !(params[0] instanceof CacheKeyDemo.CatalogQuery q)) {
                throw new IllegalArgumentException(
                        "Expected exactly one CatalogQuery");
            }
            return CacheKeyDemo.cacheKey(q);
        };
    }
}
~~~

Ví dụ service sử dụng **cùng một key contract** cho đọc và invalidation:

~~~java
@Cacheable(cacheNames = "catalogViews",
           keyGenerator = "catalogQueryKeyGenerator")
public CatalogView load(CacheKeyDemo.CatalogQuery query) {
    return repository.load(query);
}

@CacheEvict(cacheNames = "catalogViews",
            keyGenerator = "catalogQueryKeyGenerator")
public void invalidate(CacheKeyDemo.CatalogQuery query) {
    // Kích hoạt xóa sau khi xử lý nghiệp vụ thành công.
}
~~~

Hai method service ở trên là **snippet**, cần nằm trong bean do Spring quản lý, có `repository` và `CatalogView` thực tế; không thể biên dịch riêng hai method đó như file độc lập. Nếu dùng `@CachePut` để làm mới cùng entry, cũng phải dùng cùng tên cache và đúng key logic.

Các điểm cần kiểm tra khi tích hợp:

1. `@EnableCaching` được cấu hình; method được gọi **qua Spring AOP proxy** (self-invocation thường bỏ qua cache advice trong proxy mode).
2. Không dùng đồng thời `key` và `keyGenerator` trên cùng annotation; Spring coi hai thuộc tính này loại trừ nhau.
3. `@Cacheable`, `@CachePut` và `@CacheEvict` dùng cùng contract, nếu chúng tác động cùng entry. Đừng dùng một method với key `tenant:sku` và method khác chỉ dùng `sku` rồi mong invalidate đúng.
4. `CacheManager`/`CacheResolver` phải trỏ tới đúng cache. Ví dụ trên dùng `ConcurrentMapCacheManager` trong cùng tiến trình. Với Redis hay backend khác, phải kiểm tra serializer, tiền tố key, TTL và giới hạn kích thước cụ thể.
5. `KeyGenerator` nhận `target`, `method`, `params`; nếu generator dùng chung cho nhiều method thì có thể phải bao gồm danh tính method có kiểm soát hoặc cấu hình từng operation. Không mặc định dùng `method.toString()` vì chuỗi reflection có thể thay đổi theo chữ ký/version.

Một ưu điểm của **key schema riêng** là client đọc, cập nhật và xóa dùng cùng một hợp đồng. Mặt trái là cần migration có chủ đích mỗi khi hợp đồng đó đổi.

## 8. Thiết kế cho nhiều instance và cache backend

### 8.1. Local cache khác distributed cache

Với `ConcurrentMapCache`, key object được map so sánh theo `equals()/hashCode()` trong một JVM. Với Redis, key cuối cùng cần biến thành bytes. Có provider sẽ nối cache name với key, dùng `toString()`, serializer được cấu hình hoặc chiến lược khác. **Không có bảo đảm** hai key object có equality giống nhau trong JVM sẽ luôn có cùng biểu diễn bytes qua các serializer.

Để chia sẻ cache qua service instance:

- Dùng cùng schema/version và charset (thường UTF-8).
- Chốt cách normalize, định dạng số, thời gian, locale, `null`, sorting, endianness, độ dài field và phép hash.
- Đảm bảo cùng implementation/key policy được triển khai ở các phiên bản phục vụ đồng thời.
- Dùng integration test chống hồi quy so sánh exact bytes/hex với test vector cố định giữa các phiên bản. Kiểm tra cả key đọc/put/evict, đặc biệt khi rollback.
- Không dùng `System.identityHashCode()`, `Object.toString()` mặc định hoặc Java object identity làm key phân tán.

### 8.2. Cardinality và cache pollution

Key có 81 byte vẫn có thể làm cache quá tải nếu mỗi input tạo giá trị mới. Ví dụ các query chứa timestamp chính xác tới microsecond hoặc `traceId` sẽ gần như không có hit. Ngược lại, nếu loại bỏ filter quan trọng để giảm cardinality, hệ thống có thể trả kết quả không đúng.

Quy trình cân bằng: xác định các chiều thực sự ảnh hưởng kết quả → cố định/chuẩn hóa các chiều có ý nghĩa → giới hạn độ dài và số giá trị hợp lệ → cân nhắc có nên cache trường hợp quá đặc biệt → đo hit/miss, entry count và eviction rate. Với query tổ hợp quá lớn, một số endpoint có thể nên **không cache** thay vì cố xây một key.

### 8.3. Bảo mật và multi-tenant

Tenant phải được phân biệt trong key nếu vùng cache chứa nhiều tenant. Tuy nhiên, key không thay thế việc xác thực và kiểm tra quyền trong business method hoặc tầng service. Với dữ liệu người dùng, hãy tránh đưa email, access token, số giấy tờ và thông tin riêng tư nguyên văn vào key/log/metric. Có thể dùng ID nội bộ không nhạy cảm, HMAC của dữ liệu canonical hoặc cache riêng theo scope, tùy mức bảo vệ cần thiết.

Không biến key thành phương tiện truyền bí mật. Nếu phải dùng HMAC, secret và version key rotation phải đồng bộ giữa các node; thay secret khiến khóa mới không còn đọc được entry cũ và cần chiến lược migration/TTL. Thêm một salt ngẫu nhiên mỗi lần gọi sẽ phá tính ổn định.

## 9. Chiến lược kiểm thử key trước khi triển khai

Không chỉ kiểm tra `hashCode()` hoặc một lần cache hit. Nên kiểm tra các tính chất sau:

| Tính chất | Dữ liệu kiểm thử | Kỳ vọng |
| --- | --- | --- |
| Determinism | Gọi generator hai lần với cùng input | Key byte-for-byte bằng nhau |
| Equality theo nghiệp vụ | Tags đảo thứ tự khi tags là tập | Cùng key |
| Phân biệt ngữ cảnh | Đổi tenant, SKU, locale hoặc filter làm đổi kết quả | Key khác |
| Defensive copy | Sửa danh sách gốc sau khi tạo record | Key của snapshot không đổi |
| Unambiguous encoding | Các cặp `("ab","c")` và `("a","bc")` | Bytes canonical khác |
| Null/empty | Null, rỗng và thiếu trường | Bị từ chối hoặc mã hóa khác đúng theo spec |
| Unicode | Ký tự tiếng Việt, emoji, dạng Unicode tương đương | Quy tắc normalize và độ dài UTF-8 đúng |
| Length bounds | Field dài hơn giới hạn, quá nhiều tags | Bị chặn trước khi tạo key backend |
| Cross-node | Cùng input chạy ở hai node/version được hỗ trợ | Cùng bytes và namespace |
| Eviction symmetry | `@Cacheable` và `@CacheEvict` cho cùng danh tính | Evict đúng entry |
| Schema migration | v1 và v2 | Không vô tình tái sử dụng key không tương thích |
| Provider compatibility | Local map, Redis/remote serializer | Lookup/put/evict đúng theo định dạng đã chọn |

Với Java 17, chạy ví dụ phần 6 để chứng minh ba trường hợp cơ bản. Trong test cho Spring, còn cần kích hoạt `@EnableCaching`, lấy service qua application context, gọi hai lần và đếm số lần method thực sự chạy. Test remote backend nên so sánh *serialized key bytes* hoặc actual key ở provider chứ không chỉ so sánh object Java.

**Test vector cố định** đặc biệt hữu ích: chọn một bộ input bất biến và ghi nhận exact canonical bytes/digest trong unit test. Nếu người sửa code vô tình đổi `strip`, thứ tự tags, charset hoặc version, test sẽ phát hiện. Khi cố ý thay đổi quy ước, cập nhật cả schema version và kế hoạch vô hiệu hóa dữ liệu cũ.

## 10. Các lỗi phổ biến và cách khắc phục

**Lỗi 1 — Truyền mutable DTO/array làm key.** DTO thay đổi sau khi put; array có equality khác kỳ vọng. Khắc phục: snapshot thành immutable value object; chuyển array thành danh sách giá trị bất biến hoặc encode nội dung rõ ràng.

**Lỗi 2 — Chỉ dùng `productId` khi kết quả phụ thuộc tenant/locale/permission.** Hai lời gọi có thể lấy chung bản cache. Khắc phục: liệt kê tất cả chiều ảnh hưởng kết quả, gắn scope bảo mật phù hợp, kiểm thử đổi từng chiều.

**Lỗi 3 — Ghép key bằng dấu phân cách không escape.** Cặp field khác nhau có thể tạo cùng chuỗi. Khắc phục: length prefix, structured canonical format hoặc encoding với escape chuẩn và kiểm thử các ký tự đặc biệt.

**Lỗi 4 — Dựa vào `toString()` hay Java `hashCode()`.** String không đại diện đầy đủ cho identity hoặc hash quá ngắn. Khắc phục: explicit schema + UTF-8 + digest mật mã nếu cần fixed length.

**Lỗi 5 — Mã hóa không thống nhất giữa các node.** Thứ tự map, locale hệ điều hành, timezone mặc định, serializer và bản phát hành thay đổi key. Khắc phục: quy định canonical representation chính xác, không phụ thuộc locale/timezone mặc định, thêm version, kiểm thử byte-for-byte.

**Lỗi 6 — Hash dữ liệu đầu vào tùy ý không giới hạn.** Key đầu ra ngắn nhưng mọi request phải parse/hash payload lớn; cache vẫn bị bùng số entry. Khắc phục: validate giới hạn input, số trường, số tổ hợp và giá trị được phép cache **trước** khi hash.

**Lỗi 7 — Bỏ raw PII vào key “để debug”.** Key có thể xuất hiện trong log/provider. Khắc phục: không log raw secret, chọn scope/ID phù hợp hoặc HMAC khi cần; kiểm soát quyền truy cập cache.

**Lỗi 8 — Đổi logic tạo key mà không version hóa.** Cache miss tăng hàng loạt, eviction không tìm được entry cũ hoặc schema cũ bị hiểu nhầm. Khắc phục: version prefix và chiến lược transition/clear/TTL.

**Lỗi 9 — Cache entry quá lớn dù key rất ngắn.** Giới hạn key chỉ ảnh hưởng định danh; kích thước **value** và số lượng entries là ngân sách khác. Khắc phục: theo dõi cache memory, max entries, payload size và eviction chính sách provider.

**Lỗi 10 — Tưởng hash có nghĩa là không thể va chạm và tự bảo mật.** Digest hữu hạn vẫn có khả năng collision theo lý thuyết; SHA-256 thuần dễ bị đoán với miền input nhỏ. Khắc phục: chọn digest đủ mạnh và HMAC khi cần tính bí mật chống thử từ điển; xem xét collision policy theo mức độ rủi ro.

## 11. Checklist thiết kế một key mới

Trước khi thêm `@Cacheable` cho một method, hãy trả lời:

1. Điều gì khiến **kết quả khác nhau** trong khoảng TTL? Có tenant, locale, feature flag, authorization scope, sorting, pagination, phiên bản model hoặc data revision không?
2. Những tham số nào thực sự tạo danh tính? Quy tắc xử lý null, blank, uppercase, số, timezone, Unicode và collection đã thống nhất chưa?
3. Key đã bất biến chưa, kể cả thành phần bên trong record/list/map và những đối tượng bên thứ ba?
4. Định dạng có escape/length rõ ràng, version và namespace không? Tất cả node có tạo ra cùng bytes không?
5. Độ dài **byte** thực tế của key bao nhiêu, ngân sách bao nhiêu và provider thêm overhead gì? Input tối đa và cardinality tối đa là bao nhiêu?
6. `@CachePut`/`@CacheEvict`/job invalidation có tạo cùng key không? Có kế hoạch khi schema thay đổi không?
7. Key có lộ thông tin riêng tư, bí mật hoặc tạo đường truy cập chéo tenant không?
8. Đã có unit test, test vector ổn định và integration test qua backend thật chưa?

## 12. Tài liệu tham khảo

- [Spring Framework — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html): key mặc định, tùy biến `key` và `keyGenerator`, chính sách annotation.
- [SimpleKeyGenerator Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/interceptor/SimpleKeyGenerator.html): quy tắc trả argument/`SimpleKey` và tính phù hợp với provider.
- [SimpleKey Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/interceptor/SimpleKey.html): đối tượng compound key, equality và hash.
- [KeyGenerator Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/interceptor/KeyGenerator.html): hợp đồng tạo key từ target, method và parameters.
- [Java SE 17 — MessageDigest](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigest.html), [HexFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HexFormat.html) và [DataOutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataOutputStream.html): cơ sở xây dựng biểu diễn canonical có kích thước dự đoán được.

**Nguyên tắc áp dụng:** xác định danh tính theo nghiệp vụ → snapshot bất biến → chuẩn hóa theo contract → mã hóa không nhập nhằng, có version → giới hạn input và key bằng byte → dùng cùng contract cho get/put/evict → kiểm thử trên backend thực tế.