# Xây dựng khóa nghiệp vụ có nhiều trường trong Java

## 1. Bài toán thực tế: một trường chưa đủ xác định đối tượng

Trong nhiều hệ thống, một mã có thể trùng giữa các khách hàng, kênh tích hợp hoặc phạm vi nghiệp vụ. Ví dụ, mã hóa đơn **INV-0042** có thể xuất hiện ở cả hai tenant; cùng một tenant còn có thể nhận mã đó từ hai hệ thống nguồn khác nhau.

Giả sử quy tắc nghiệp vụ đã được xác nhận:

> Một hóa đơn được nhận diện duy nhất bằng **(tenantId, sourceSystem, externalNumber)**. Cả ba trường đều bắt buộc; hệ thống coi các mã này không phân biệt chữ hoa/chữ thường và bỏ khoảng trắng thừa ở hai đầu.

Bộ ba đó là một **khóa nghiệp vụ ghép (composite business key)**. Nó biểu diễn *cùng một thực thể theo ý nghĩa nghiệp vụ*, kể cả khi hai đối tượng Java được tạo ở hai thời điểm khác nhau.

Ví dụ:

| tenantId | sourceSystem | externalNumber | Cùng khóa với hàng đầu? |
| --- | --- | --- | --- |
| SHOP-A | ERP | INV-0042 | Chính nó |
| shop-a | erp | inv-0042 | Có, theo quy tắc chuẩn hóa đã chọn |
| SHOP-B | ERP | INV-0042 | Không: tenant khác |
| SHOP-A | WEB | INV-0042 | Không: nguồn khác |
| SHOP-A | ERP | INV-0099 | Không: số hóa đơn khác |

Nếu chỉ dùng **externalNumber** làm khóa của **Map** hoặc làm điều kiện chống trùng, dữ liệu từ các tenant/nguồn khác nhau có thể ghi đè nhau. Nếu dùng nối chuỗi tùy tiện để tạo khóa, ta còn gặp rủi ro nhập nhằng và khó bảo trì.

Trong Java, lời giải thường là tạo **một kiểu dữ liệu dành riêng cho khóa**, định nghĩa tập trường tham gia so sánh, chuẩn hóa giá trị ở đầu vào, và bảo đảm **equals()/hashCode()** nhất quán.

## 2. Phân biệt khóa nghiệp vụ và khóa kỹ thuật

**Khóa nghiệp vụ** là tổ hợp thuộc tính có ý nghĩa với người sử dụng hoặc hệ thống tích hợp: tenant, nguồn, mã đối tác, ngày hiệu lực... Ví dụ **(tenantId, sourceSystem, externalNumber)**.

**Khóa kỹ thuật** là định danh hệ thống sinh ra, thường là **id** tăng dần hoặc **UUID**, phục vụ lưu trữ, tham chiếu nội bộ hay khóa chính của cơ sở dữ liệu.

Một hóa đơn có thể có:

- **id = 98217**: khóa kỹ thuật nội bộ.
- **(SHOP-A, ERP, INV-0042)**: khóa nghiệp vụ để tìm hóa đơn nhận từ ERP của tenant SHOP-A.

Hai loại khóa không loại trừ nhau. Một thiết kế phổ biến là dùng **id** làm khóa chính và áp dụng ràng buộc **UNIQUE** cho bộ ba nghiệp vụ. Khi số hóa đơn hoặc quy tắc nghiệp vụ có thể thay đổi, cần làm rõ khóa đó đại diện cho danh tính ổn định hay chỉ là khóa tra cứu/chống nhập trùng tại một thời điểm.

Một khóa ghép tốt phải trả lời được: **“Thay đổi đúng một trường trong bộ này có làm đối tượng trở thành thực thể khác không?”** Nếu có, trường đó thường thuộc khóa; nếu không, nhiều khả năng đó là thuộc tính thông thường.

## 3. Hợp đồng equals() và hashCode() đối với khóa ghép

**HashMap**, **HashSet** và các cấu trúc dựa trên hash sử dụng **hashCode()** để phân bố phần tử và **equals()** để xác định hai khóa có cùng danh tính hay không. Vì vậy:

1. **Phản xạ:** với khóa hợp lệ **a**, **a.equals(a)** là **true**.
2. **Đối xứng:** **a.equals(b)** và **b.equals(a)** có cùng kết quả.
3. **Bắc cầu:** nếu **a.equals(b)** và **b.equals(c)** thì **a.equals(c)**.
4. **Nhất quán:** khi những giá trị tham gia so sánh không đổi, gọi **equals()** nhiều lần phải cho cùng kết quả.
5. **So sánh với null:** **a.equals(null)** là **false**.
6. **Tương thích hash:** nếu **a.equals(b)** là **true** thì **a.hashCode() == b.hashCode()** phải đúng.

Chiều ngược lại **không bắt buộc**: hai khóa *khác nhau* có thể trùng hash vì va chạm hash là bình thường. Do đó không được xem **hashCode()** là mã định danh duy nhất và không dùng riêng giá trị hash để xác nhận trùng dữ liệu.

Khi xây khóa từ ba trường, cả ba trường phải có mặt trong phép so sánh danh tính; việc bỏ sót **sourceSystem** ở **equals()** hoặc **hashCode()** có thể tạo lỗi khó phát hiện. Đồng thời các trường tham gia hash cần **ổn định suốt thời gian khóa nằm trong Map/Set**.

## 4. Giải pháp Java 17+: dùng record bất biến

**record** phù hợp với khóa nghiệp vụ gồm những thành phần giá trị đơn giản. Java tự sinh constructor chuẩn, accessor, **equals()**, **hashCode()** và **toString()** dựa trên toàn bộ các thành phần của record. Ta có thể bổ sung compact canonical constructor để xác thực và chuẩn hóa đầu vào trước khi lưu.

Ví dụ hoàn chỉnh, lưu trong tệp **InvoiceKeyDemo.java**:

~~~java
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;

public class InvoiceKeyDemo {
    public record InvoiceKey(
            String tenantId,
            String sourceSystem,
            String externalNumber) {

        // Compact canonical constructor:
        // chuẩn hóa trước khi Java gán vào các trường của record.
        public InvoiceKey {
            tenantId = normalize("tenantId", tenantId);
            sourceSystem = normalize("sourceSystem", sourceSystem);
            externalNumber = normalize("externalNumber", externalNumber);
        }

        private static String normalize(String field, String value) {
            Objects.requireNonNull(value, field + " must not be null");
            String result = value.strip().toUpperCase(Locale.ROOT);
            if (result.isEmpty()) {
                throw new IllegalArgumentException(field + " must not be blank");
            }
            return result;
        }
    }

    public static void main(String[] args) {
        InvoiceKey first = new InvoiceKey(
                "shop-a", "erp", " inv-0042 ");
        InvoiceKey same = new InvoiceKey(
                " SHOP-A ", "ERP", "INV-0042");
        InvoiceKey otherTenant = new InvoiceKey(
                "shop-b", "erp", "INV-0042");
        InvoiceKey otherSource = new InvoiceKey(
                "shop-a", "web", "INV-0042");

        Map<InvoiceKey, String> states = new HashMap<>();
        states.put(first, "NEW");
        states.put(same, "PAID");
        states.put(otherTenant, "NEW");
        states.put(otherSource, "REVIEW");

        System.out.println("same identity: " + first.equals(same));
        System.out.println("same hash: "
                + (first.hashCode() == same.hashCode()));
        System.out.println("different tenant: "
                + first.equals(otherTenant));
        System.out.println("different source: "
                + first.equals(otherSource));
        System.out.println("size: " + states.size());
        System.out.println("normalized: " + first);
        System.out.println("lookup: " + states.get(
                new InvoiceKey("SHOP-A", "ErP", "inv-0042")));
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac InvoiceKeyDemo.java
java InvoiceKeyDemo
~~~

Kết quả chuẩn:

~~~text
same identity: true
same hash: true
different tenant: false
different source: false
size: 3
normalized: InvoiceKey[tenantId=SHOP-A, sourceSystem=ERP, externalNumber=INV-0042]
lookup: PAID
~~~

**Giải thích:** Hai đối tượng **first** và **same** khác tham chiếu nhưng giống nhau về danh tính nghiệp vụ sau chuẩn hóa. Lệnh **put(same, "PAID")** thay thế giá trị của khóa tương đương đã tồn tại nên **size** chỉ là **3**, không phải **4**. Hai hóa đơn khác tenant hoặc khác nguồn vẫn được lưu riêng. Lệnh tra cứu cuối cùng tạo một đối tượng khóa mới nhưng vẫn tìm đúng trạng thái **PAID**.

Mã trên dùng quy tắc **bỏ khoảng trắng hai đầu + không phân biệt hoa/thường cho cả ba trường** vì đó là giả định nghiệp vụ đã nêu. **Không áp dụng chuẩn hóa này một cách máy móc**: nếu tenantId, mã có chữ hoa/chữ thường, hoặc externalNumber thực sự phân biệt ký tự, chuyển đổi chữ hoa có thể gộp nhầm hai thực thể.

### Vì sao record hữu ích?

- **final theo bản chất:** không tạo subclass để thay đổi hành vi equality.
- **Thành phần cố định:** các field của record được gán một lần khi tạo đối tượng.
- **Ít code thủ công:** không phải viết lại equals/hashCode/toString dễ thiếu trường.
- **Rõ nghĩa:** accessor **tenantId()**, **sourceSystem()** và **externalNumber()** cho biết thành phần của khóa.
- **Dễ dùng làm key:** các thành phần đều là **String** bất biến, nên giá trị khóa không bị đổi sau khi đưa vào HashMap.

Lưu ý: record chỉ bảo đảm **bất biến nông (shallow immutability)**. Nếu thành phần là mảng, danh sách hay đối tượng mutable, nội dung bên trong chúng vẫn có thể đổi. Ví dụ **record Key(byte[] bytes)** không tự sao chép mảng và phép so sánh mảng mặc định theo tham chiếu; không nên dùng trực tiếp như khóa theo nội dung byte nếu chưa có thiết kế sao chép/phép so sánh phù hợp.

## 5. Khi cần dùng class: triển khai equals/hashCode đồng bộ

Nếu không dùng record (chẳng hạn cần một lớp có khả năng tùy biến constructor, cách trình bày API khác, hoặc đang ở codebase cũ), hãy thiết kế một **final class** với field **private final**, constructor kiểm tra đầu vào, và cả **equals()** lẫn **hashCode()** dựa trên cùng bộ trường.

Ví dụ Java 17 chạy độc lập trong **InvoiceKeyClassDemo.java**:

~~~java
import java.util.HashSet;
import java.util.Locale;
import java.util.Objects;
import java.util.Set;

public class InvoiceKeyClassDemo {
    public static final class InvoiceKey {
        private final String tenantId;
        private final String sourceSystem;
        private final String externalNumber;

        public InvoiceKey(
                String tenantId, String sourceSystem, String externalNumber) {
            this.tenantId = normalize(tenantId);
            this.sourceSystem = normalize(sourceSystem);
            this.externalNumber = normalize(externalNumber);
        }

        private static String normalize(String value) {
            Objects.requireNonNull(value, "key component");
            String result = value.strip().toUpperCase(Locale.ROOT);
            if (result.isEmpty()) {
                throw new IllegalArgumentException("Blank key component");
            }
            return result;
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof InvoiceKey other)) {
                return false;
            }
            return tenantId.equals(other.tenantId)
                    && sourceSystem.equals(other.sourceSystem)
                    && externalNumber.equals(other.externalNumber);
        }

        @Override
        public int hashCode() {
            return Objects.hash(tenantId, sourceSystem, externalNumber);
        }
    }

    public static void main(String[] args) {
        InvoiceKey a = new InvoiceKey("shop-a", "erp", "inv-0042");
        InvoiceKey b = new InvoiceKey("SHOP-A", "ERP", " INV-0042 ");
        InvoiceKey c = new InvoiceKey("shop-a", "web", "inv-0042");

        Set<InvoiceKey> keys = new HashSet<>();
        keys.add(a);
        keys.add(b);

        System.out.println("equal: " + a.equals(b));
        System.out.println("same hash: " + (a.hashCode() == b.hashCode()));
        System.out.println("other source equal: " + a.equals(c));
        System.out.println("set size: " + keys.size());
    }
}
~~~

~~~bash
javac InvoiceKeyClassDemo.java
java InvoiceKeyClassDemo
~~~

Kết quả chuẩn:

~~~text
equal: true
same hash: true
other source equal: false
set size: 1
~~~

**Objects.hash(...)** tính hash từ nhiều thành phần; không bắt buộc dùng thuật toán này, nhưng phải dùng **đúng các trường** xuất hiện trong **equals()**. Với khóa gồm trường bất biến, không cần tự cache hash trừ khi đã đo được nhu cầu; việc cache sai hoặc dựa trên field mutable dễ làm hỏng hợp đồng. Có thể dùng **instanceof** an toàn ở đây vì lớp khóa được khai báo **final**, nên không có subclass làm thay đổi quan hệ đối xứng.

## 6. Chọn đúng các trường tham gia khóa

Thiết kế key phải bắt đầu từ **quy tắc nhận diện**, không bắt đầu từ danh sách field đang có trong entity.

Ví dụ một bản ghi hóa đơn có thể chứa:

| Trường | Tham gia InvoiceKey? | Lý do |
| --- | --- | --- |
| tenantId | Có | Cùng số hóa đơn giữa tenant là hai hóa đơn khác nhau |
| sourceSystem | Có | ERP và WEB có namespace mã riêng |
| externalNumber | Có | Mã hóa đơn trong phạm vi tenant + nguồn |
| status | Không | Trạng thái NEW/PAID có thể thay đổi |
| totalAmount | Không | Tổng tiền có thể điều chỉnh |
| updatedAt | Không | Thời gian sửa đổi không phải danh tính |
| databaseId | Không trong business key | Định danh nội bộ, thuộc mô hình lưu trữ |
| displayName | Không | Tên hiển thị không xác định bản ghi |

Các câu hỏi cần xác minh cùng domain owner:

1. Một bộ giá trị có thể được tái sử dụng cho **hai thực thể khác nhau qua thời gian** không? Nếu có, có cần thêm loại phiên bản/ngày hiệu lực, hoặc không nên dùng nó làm danh tính bất biến?
2. Giá trị nào được xác định ngay khi tạo, giá trị nào chỉ xuất hiện sau khi quy trình hoàn tất? Khóa thiếu thành phần lúc đầu cần có chiến lược rõ ràng.
3. Tenant, region, provider, môi trường hoặc kênh nguồn có chia namespace độc lập không?
4. Giá trị có phân biệt hoa/thường, khoảng trắng, dấu tiếng Việt, Unicode hoặc số 0 ở đầu không?
5. Có trường nào thay đổi sau khi khóa đã được dùng để tra cứu, cache hoặc đồng bộ không?

Nếu một trường hợp pháp có thể đổi mà **vẫn đại diện cùng thực thể**, không nên dùng trường đó làm khóa định danh ổn định trong cache lâu dài. Có thể dùng **id** kỹ thuật cho identity và để business key đóng vai trò điều kiện lookup; xử lý việc thay đổi business key như thay đổi chỉ mục/ánh xạ chứ không tự giả định entity mới.

## 7. Chuẩn hóa và validation: định nghĩa thế nào là “bằng nhau”?

Chuẩn hóa tốt giúp loại bỏ khác biệt nhập liệu không mang ý nghĩa nghiệp vụ. Chuẩn hóa sai lại gây **mất thông tin** hoặc trộn nhầm khóa.

| Dữ liệu | Quyết định cần được chốt | Ví dụ |
| --- | --- | --- |
| Khoảng trắng đầu/cuối | Có bỏ không? | " INV-1 " → "INV-1" nếu khoảng trắng không mang nghĩa |
| Hoa/thường | Có phân biệt không? | "erp" = "ERP" nếu cùng mã nguồn |
| Unicode | Có chuẩn hóa NFC/NFKC không? | Ký tự có dấu biểu diễn theo nhiều chuỗi mã |
| Số 0 ở đầu | Có mang nghĩa không? | "0007" và "7" có thể là hai mã khác |
| Giá trị null/trống | Cấm hay có ý nghĩa? | tenantId null thường phải bị từ chối |
| Kiểu số | Số thực hay mã định danh? | "1.0" và "1.00" có thể khác khi là mã |
| Thời gian | Mốc tức thời hay ngày tại múi giờ nghiệp vụ? | LocalDate khác Instant |
| Phân tách chuỗi | Có escaping và schema không? | ("AB","C") khác ("A","BC") |

Một số nguyên tắc kỹ thuật:

- **String.strip()** (Java 11+) loại bỏ khoảng trắng Unicode theo định nghĩa của Java ở hai đầu; **String.trim()** có phạm vi xử lý ký tự khác. Chọn theo đầu vào thực tế.
- **toUpperCase(Locale.ROOT)** tránh phụ thuộc locale mặc định của máy, nhưng vẫn có thể làm hai mã khác nhau trở nên giống nhau. Quy tắc không phân biệt hoa/thường phải do nghiệp vụ quyết định và phải phù hợp với cách hệ thống khác xử lý mã.
- Với Unicode có nhiều cách biểu diễn tương đương, có thể cân nhắc **java.text.Normalizer** theo chuẩn NFC khi thật sự cần; không tự dùng NFKC nếu việc gộp ký tự tương thích làm mất phân biệt nghiệp vụ.
- Với **BigDecimal**, **new BigDecimal("1.0").equals(new BigDecimal("1.00"))** là **false** vì scale khác; **compareTo(...) == 0** lại là **true**. Nếu giá trị số là thành phần khóa, xác định rõ ý nghĩa scale trước khi chọn dạng chuẩn, tránh sửa equality rời rạc.
- Với ngày giờ, dùng kiểu bất biến thích hợp (**LocalDate**, **Instant**, ...), quy định múi giờ tại ranh giới chuyển đổi thay vì lấy múi giờ mặc định khác nhau giữa các máy.
- Với khóa nullable, quyết định null có hợp lệ hay không trước khi viết **equals()**. Nếu có trường tùy chọn, phải nêu rõ sự vắng mặt tác động thế nào đến uniqueness; nhiều cơ sở dữ liệu xử lý **NULL** trong ràng buộc UNIQUE khác với so sánh Java.

**Validation đặt ngay tại lúc tạo khóa** có lợi vì sau đó mọi đối tượng khóa hợp lệ đều tuân cùng quy tắc. Nếu app, batch import và database dùng ba cách chuẩn hóa khác nhau, việc chống trùng sẽ không nhất quán. Tốt nhất nên có một chính sách chuẩn hóa được kiểm thử, áp dụng tại boundary và phản ánh vào cách lưu/index dữ liệu.

## 8. Vì sao không dùng nối chuỗi làm khóa tùy tiện?

Đoạn mã sau dễ gây nhầm lẫn:

~~~java
// Minh họa lỗi, không phải chương trình độc lập:
String key = tenantId + sourceSystem + externalNumber;
~~~

Các bộ thành phần **("AB", "C", "D")** và **("A", "BC", "D")** đều thành **"ABCD"**. Dùng delimiter đơn giản cũng có thể đụng độ nếu một thành phần tự chứa delimiter:

~~~java
// Cũng chỉ là minh họa:
String key = tenantId + "|" + sourceSystem + "|" + externalNumber;
~~~

Nếu trường chứa ký tự **|**, không có quy tắc escaping/độ dài, chuỗi sẽ khó phân tách và có thể nhập nhằng. Dùng khóa kiểu dữ liệu như **record InvoiceKey(...)** để Java so sánh **từng thành phần**. Nếu bắt buộc phải truyền khóa qua URL, message hoặc persistence bằng chuỗi, hãy thiết kế **serialization không nhập nhằng**: độ dài từng phần, định dạng cấu trúc có schema, escaping có quy tắc và phiên bản định dạng. Đó là vấn đề mã hóa/đọc lại khóa, tách biệt với hợp đồng equality của object.

Tương tự, không dùng **Arrays.toString(...)** hoặc **Objects.hash(...)** làm “mã khóa duy nhất”: biểu diễn text không mặc nhiên là định dạng bất biến, còn hash có thể trùng giữa hai khóa khác nhau.

## 9. Lỗi nguy hiểm: thay đổi khóa sau khi đưa vào HashMap

Xét tình huống giả định với một lớp khóa có trường **externalNumber** có thể gán lại:

~~~java
// Mã minh họa hành vi không an toàn:
MutableInvoiceKey key = new MutableInvoiceKey("SHOP-A", "ERP", "INV-1");
map.put(key, invoice);
key.setExternalNumber("INV-2");
Invoice result = map.get(key); // Có thể không tìm thấy
~~~

Đây **không phải chương trình Java độc lập**: **MutableInvoiceKey**, **Invoice** và **map** chỉ là các kiểu/biến minh họa. Khi giá trị tham gia **hashCode()** đổi sau lệnh **put**, bucket cũ của HashMap không tự được xây lại; tìm kiếm có thể trả về **null** hoặc gặp trạng thái khó dự đoán. **HashSet** cũng chịu vấn đề tương tự.

Cách xử lý đúng:

- Dùng khóa bất biến như **record** hoặc **final class** với field final chứa giá trị bất biến.
- Nếu nghiệp vụ cần đổi mã, tạo **khóa mới**; gỡ ánh xạ cũ và thêm ánh xạ mới theo một thao tác có kiểm soát.
- Nếu cache lưu entity mutable, có thể giữ **business key immutable** tách khỏi entity; đừng dùng trực tiếp một entity mà equals/hashCode dựa vào field có thể đổi.
- Đối với nội dung collection hoặc array, cần defensive copy và so sánh theo ngữ nghĩa thực tế, không chỉ đặt tham chiếu vào field final.

Một **final field** trỏ đến **List** vẫn cho phép **List** bị sửa nếu không có cơ chế sao chép/bất biến tương ứng.

## 10. HashMap không thay thế ràng buộc UNIQUE của database

Ví dụ ở mục 4 chứng minh **HashMap** gộp các đối tượng khóa tương đương trong **một tiến trình**. Nó không bảo đảm không có hai request, hai JVM hoặc hai worker cùng ghi hai hóa đơn trùng business key vào cơ sở dữ liệu.

Nếu ba cột đã chuẩn hóa là khóa nghiệp vụ, một thiết kế SQL minh họa là:

~~~sql
CREATE TABLE invoices (
    id BIGINT PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    source_system VARCHAR(64) NOT NULL,
    external_number VARCHAR(120) NOT NULL,
    status VARCHAR(20) NOT NULL,
    CONSTRAINT uq_invoice_business
        UNIQUE (tenant_id, source_system, external_number)
);
~~~

Đây là **schema SQL minh họa**, cú pháp chi tiết và cách sinh **id** tùy hệ quản trị. Ứng dụng phải lưu dạng chuẩn hóa thống nhất hoặc thiết kế chỉ mục/collation tương ứng; nếu database so sánh khác Java, hai lớp có thể cho kết quả uniqueness khác nhau.

Không thể chống duplicate đáng tin chỉ bằng:

~~~text
1. SELECT để kiểm tra chưa có
2. Nếu chưa có thì INSERT
~~~

Hai request đồng thời có thể cùng vượt qua bước kiểm tra rồi cùng INSERT. Ràng buộc UNIQUE trong database mới thực thi chống trùng giữa nhiều request đồng thời; ứng dụng cần xử lý vi phạm uniqueness/transaction và quyết định retry, trả lỗi hay idempotent response theo yêu cầu nghiệp vụ. Với luồng nhập từ bên ngoài, có thể dùng business key làm cơ sở cho cơ chế **idempotency**, nhưng vẫn phải xác định xung đột payload: trùng khóa không tự khẳng định toàn bộ nội dung request hợp lệ hoặc giống nhau.

### Trường hợp JPA/Hibernate

Đừng đồng nhất object **InvoiceKey** làm khóa tra cứu với chính sách **equals/hashCode của JPA entity**. Entity có thể có **id** kỹ thuật, proxy, trạng thái managed/detached và vòng đời khác. Nếu chọn khóa chính ghép bằng **@EmbeddedId** hoặc **@IdClass**, hãy tuân các yêu cầu riêng của JPA provider (kiểu khóa, constructor, serializable, equality, ánh xạ cột). Không tự giả định record bất kỳ dùng được trực tiếp làm JPA embeddable trên mọi phiên bản/provider. Ngay cả khi database dùng khóa chính kỹ thuật, vẫn có thể có **UNIQUE (tenant_id, source_system, external_number)** để bảo toàn quy tắc nghiệp vụ.

## 11. Dùng khóa ghép trong HashSet, cache và cấu trúc có thứ tự

Với **HashSet**, thêm một hóa đơn đã có cùng khóa sẽ không tăng số lượng phần tử. Với **Map/HashMap**, **put** khóa bằng nhau thay thế value đang gắn với khóa đó. Điều này khác với database: **put** ghi đè là hành vi bình thường của Map, còn ghi trùng UNIQUE thường là một lỗi hoặc nhánh xử lý có chủ đích. Không để việc ghi đè trong cache che khuất sự kiện nghiệp vụ cần báo lỗi.

Nếu dùng **TreeMap** hoặc **TreeSet**, ngoài equals/hashCode còn phải định nghĩa **Comparator** hoặc **Comparable**. Comparator phải xét đúng cùng các thành phần quyết định identity; nếu **compare(a,b) == 0** với hai khóa mà **!a.equals(b)**, cấu trúc có thứ tự có thể coi chúng là một key và làm mất phần tử theo cách bất ngờ.

Ví dụ **đoạn mã minh họa** dùng record đã định nghĩa ở mục 4:

~~~java
import java.util.Comparator;

Comparator<InvoiceKeyDemo.InvoiceKey> byKey =
        Comparator.comparing(InvoiceKeyDemo.InvoiceKey::tenantId)
                .thenComparing(InvoiceKeyDemo.InvoiceKey::sourceSystem)
                .thenComparing(InvoiceKeyDemo.InvoiceKey::externalNumber);
~~~

Đoạn này cần đặt trong phạm vi cho phép khai báo biến (như method) và ở cùng package/đường dẫn class thích hợp. Vì tất cả thành phần đã là **String** chuẩn hóa, so sánh theo cùng ba trường cho kết quả bằng không khi record bằng nhau. Nếu so sánh không phân biệt hoa/thường lại áp dụng trên các giá trị gốc chưa chuẩn hóa, phải kiểm tra kỹ sự tương thích với **equals()**.

Với cache nhiều tenant, **tenantId** luôn là phần của lookup khi domain cần cô lập tenant; lỗi bỏ tenant khỏi khóa cache có thể dẫn đến trả nhầm dữ liệu giữa khách hàng.

## 12. Chiến lược kiểm thử khóa ghép

Một bộ kiểm thử tối thiểu nên kiểm tra cả **phép so sánh** lẫn **hành vi trong collection**, thay vì chỉ so hash:

| Ca kiểm thử | Kết quả mong đợi |
| --- | --- |
| Hai bộ ba giống hệt | equals true, hash bằng nhau |
| Khác nhau chỉ bởi hoa/thường/space theo chính sách | equals true sau chuẩn hóa |
| Khác đúng tenantId | equals false |
| Khác đúng sourceSystem | equals false |
| Khác đúng externalNumber | equals false |
| null/trống ở trường bắt buộc | Constructor từ chối với exception rõ |
| Thêm hai khóa tương đương vào HashSet | Một phần tử |
| put hai khóa tương đương vào HashMap | Value mới thay value cũ, không tăng số key |
| Tạo lại khóa từ dữ liệu đã persisted | Tra cứu ra bản ghi tương ứng |
| So sánh với null, đối tượng kiểu khác | equals false |
| Đồng thời insert duplicate ở nhiều request | Database UNIQUE chỉ cho tồn tại một khóa nghiệp vụ |

Nên có test **phản xạ, đối xứng, bắc cầu**, tính ổn định qua nhiều lần gọi và đảm bảo nếu equals true thì hash giống nhau. Có thể bổ sung **property-based tests** khi quy tắc chuẩn hóa có nhiều biến thể Unicode, khoảng trắng, tenant và nguồn tích hợp.

Ví dụ test riêng bằng Java 17, không cần thư viện ngoài, lưu tệp **InvoiceKeyChecks.java** trong cùng thư mục với **InvoiceKeyDemo.java**:

~~~java
import java.util.HashSet;
import java.util.Set;

public class InvoiceKeyChecks {
    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        var a = new InvoiceKeyDemo.InvoiceKey(
                "shop-a", "erp", "inv-0042");
        var b = new InvoiceKeyDemo.InvoiceKey(
                " SHOP-A ", "ERP", " INV-0042 ");
        var c = new InvoiceKeyDemo.InvoiceKey(
                "shop-a", "erp", "inv-0042");
        var other = new InvoiceKeyDemo.InvoiceKey(
                "shop-b", "erp", "inv-0042");

        check(a.equals(a), "reflexive");
        check(a.equals(b) && b.equals(a), "symmetric");
        check(a.equals(b) && b.equals(c) && a.equals(c),
                "transitive");
        check(a.hashCode() == b.hashCode(), "same hash");
        check(!a.equals(other), "different tenant");
        check(!a.equals(null), "not equal to null");
        check(!a.equals("not an InvoiceKey"), "different type");

        Set<InvoiceKeyDemo.InvoiceKey> set = new HashSet<>();
        set.add(a);
        set.add(b);
        set.add(other);
        check(set.size() == 2, "set identity");

        boolean rejected = false;
        try {
            new InvoiceKeyDemo.InvoiceKey("shop-a", "", "inv-1");
        } catch (IllegalArgumentException expected) {
            rejected = true;
        }
        check(rejected, "reject blank component");

        System.out.println("All composite-key checks passed.");
    }
}
~~~

Chạy:

~~~bash
javac InvoiceKeyDemo.java InvoiceKeyChecks.java
java InvoiceKeyChecks
~~~

Kết quả chuẩn:

~~~text
All composite-key checks passed.
~~~

Các kiểm thử này xác nhận hành vi cơ bản của object và collection. Bảo đảm uniqueness thực tế khi ghi dữ liệu đồng thời còn cần kiểm thử tích hợp với database thật, vì test HashMap không thể phát hiện race condition giữa nhiều transaction.

## 13. Thực hành tổng hợp: thiết kế khóa cho sản phẩm tích hợp

Một sàn thương mại điện tử nhận SKU từ các đối tác. Mỗi đối tác có thể gửi SKU giống nhau; mỗi tenant có các catalog độc lập. Một sản phẩm biến thể được xác định duy nhất bởi **(tenantId, partnerId, sku, variantCode)**.

**Yêu cầu thực hành:**

1. Quyết định rõ trường nào phân biệt hoa/thường, có bỏ khoảng trắng không, và xử lý thế nào khi **variantCode** thiếu. Viết giả định trước khi code.
2. Tạo một **record ProductKey** chứa bốn trường và validation theo quyết định đó.
3. Cho hai đối tượng khóa chỉ khác định dạng đầu vào vào **HashSet**; xác nhận gộp hay không gộp đúng quy tắc.
4. Tạo hai khóa có SKU giống nhau nhưng khác tenant hoặc partner; xác nhận chúng luôn được nhận diện riêng.
5. Tạo **Map<ProductKey, ProductData>** để tra cứu và giải thích chuyện gì xảy ra khi **put** hai khóa bằng nhau.
6. Đề xuất **UNIQUE (tenant_id, partner_id, sku, variant_code)** hoặc một ràng buộc thay thế phản ánh đúng cách lưu trường tùy chọn. Nếu variantCode cho phép null, phải kiểm tra ngữ nghĩa UNIQUE/NULL của hệ quản trị cụ thể.
7. Đánh giá xem đổi mã SKU có làm đổi danh tính sản phẩm hay chỉ đổi khóa tra cứu; từ đó quyết định có cần **id** nội bộ ổn định không.

**Gợi ý lời giải:** ưu tiên các thành phần khóa đã chuẩn hóa, bất biến; sử dụng equals/hashCode do record sinh ra; không đưa giá bán, số lượng tồn hay tên hiển thị vào key nếu chúng chỉ là thuộc tính thay đổi. Bảo vệ uniqueness tại database chứ không chỉ trong JVM. Đối với trường tùy chọn, quy định rõ “không có variant” là một giá trị duy nhất, hay là trạng thái chưa xác định cần xử lý riêng.

## 14. Checklist khi review thiết kế

Trước khi đưa composite business key vào production, tự kiểm tra:

- **Domain:** tổ hợp trường có thực sự xác định đúng một thực thể trong đúng phạm vi tenant/nguồn/thời gian?
- **Tính ổn định:** những trường tham gia khóa có thể thay đổi sau khi key được dùng không?
- **Chuẩn hóa:** có chính sách rõ cho case, whitespace, Unicode, null, số và thời gian; policy có thống nhất với database không?
- **Equality:** equals so đúng từng thành phần; hashCode dùng cùng thành phần và thỏa hợp đồng?
- **Bất biến:** record/final class có chứa field mutable nào cần copy hoặc thiết kế lại không?
- **Collection:** HashMap/HashSet có thao tác ghi đè hoặc gộp khóa nào cần xử lý nghiệp vụ riêng không?
- **Đa tenant:** mọi lookup/query/cache có đầy đủ trường định phạm vi để không đọc nhầm dữ liệu?
- **Lưu trữ và đồng thời:** database có UNIQUE phù hợp, transaction có xử lý xung đột khi hai request cùng tạo không?
- **Tương thích hệ thống:** định dạng serialization và versioning có bảo toàn các thành phần, không phụ thuộc delimiter mơ hồ?
- **Kiểm thử:** có ca cho từng trường khác biệt, chuẩn hóa, null, va chạm tiềm năng và luồng ghi cạnh tranh không?

## 15. Ghi nhớ

**Khóa nghiệp vụ nhiều trường là một mô hình danh tính, không chỉ là phép nối chuỗi.** Trước tiên xác nhận các trường nào *thực sự* xác định một đối tượng trong phạm vi nghiệp vụ. Sau đó đóng gói chúng thành **record** hoặc **final class** bất biến, áp dụng validation và chuẩn hóa thống nhất, để **equals()/hashCode()** phản ánh đúng toàn bộ thành phần khóa. Sử dụng khóa này an toàn trong Map/Set, đồng thời để database thực thi ràng buộc uniqueness khi nhiều tiến trình hoặc request ghi dữ liệu đồng thời.
