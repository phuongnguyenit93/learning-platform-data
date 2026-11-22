# Chọn dữ liệu băm phù hợp với quan hệ equals() trong Java

## 1. Vấn đề cần giải quyết

Khi tự cài đặt hai phương thức **equals(Object)** và **hashCode()**, câu hỏi quan trọng không phải là “lấy càng nhiều trường vào hash càng tốt” mà là: **những đối tượng nào được coi là bằng nhau theo equals và làm sao bảo đảm chúng luôn có cùng hashCode?**

Ví dụ, một sản phẩm có các trường:

- tenantId: cửa hàng sở hữu sản phẩm;
- sku: mã sản phẩm, quy ước không phân biệt chữ hoa/chữ thường;
- displayName: tên trình bày trên giao diện;
- lastViewedAt: thời điểm gần nhất người dùng mở trang sản phẩm.

Nếu quan hệ equals xác định cùng sản phẩm bằng cặp **(tenantId, sku sau chuẩn hóa)**, hashCode cũng phải tạo cùng kết quả đối với mọi cặp giá trị tương đương này. displayName hoặc lastViewedAt không được khiến hai sản phẩm cùng định danh có mã băm khác nhau.

Ngược lại, nếu equals thực sự so sánh cả displayName thì hashCode không thể tự ý dựa vào một quan hệ bình đẳng khác. Cần chốt **định nghĩa equality trước**, sau đó chọn dữ liệu băm phù hợp.

## 2. Hợp đồng equals–hashCode: hai nguyên tắc không thể đảo ngược

Hợp đồng Java Object.hashCode() yêu cầu:

1. **Nếu x.equals(y) là true thì x.hashCode() phải bằng y.hashCode().**
2. Khi không có thông tin nào dùng trong equals thay đổi, nhiều lần gọi hashCode trên cùng đối tượng trong một lần thực thi Java phải trả cùng số nguyên.

Điều **không** được yêu cầu:

- Hai đối tượng khác nhau theo equals phải có mã băm khác nhau. **Va chạm băm (collision) được phép xảy ra.**
- hashCode phải giống nhau giữa các lần chạy chương trình khác nhau; Java không bảo đảm mọi cách triển khai đều ổn định giữa các phiên chạy.
- hashCode phải là mã định danh duy nhất, địa chỉ bộ nhớ hay số không âm.

Có thể hình dung quan hệ bằng nhau chia các đối tượng thành những *nhóm tương đương*. Mỗi nhóm phải nhận **một** giá trị hash ổn định trong các điều kiện nêu trên; nhiều nhóm khác nhau vẫn có thể dùng chung một giá trị hash.

| Quan hệ giữa x và y | Yêu cầu đối với hashCode | Ghi chú |
| --- | --- | --- |
| x.equals(y) == true | hashCode **bắt buộc bằng nhau** | Điều kiện hợp đồng |
| x.equals(y) == false | hashCode có thể bằng hoặc khác | Không được kết luận từ hash |
| Trạng thái tham gia equals giữ nguyên | hashCode phải ổn định trong lần chạy | Không dùng random/thời gian để băm |
| Trạng thái tham gia equals bị sửa | Hash có thể đổi | Dễ gây lỗi khi đang dùng làm khóa băm |

Cần phân biệt: **“Dữ liệu tham gia equals” là dữ liệu quyết định quan hệ bằng nhau về mặt logic**, không đơn giản là “toàn bộ trường của đối tượng”.

## 3. Quy trình chọn dữ liệu để băm

### Bước 1: Xác định tiêu chí bằng nhau

Hãy trả lời trước: hai đối tượng đại diện cho cùng một giá trị khi những thuộc tính nào khớp nhau? Ví dụ:

~~~java
return tenantId.equals(other.tenantId)
        && normalizedSku.equals(other.normalizedSku);
~~~

Nếu đây là phần quyết định equality, hai đối tượng có cùng tenantId và normalizedSku phải có hash bằng nhau.

### Bước 2: Xem xét cách equals so sánh từng trường

Cùng một trường dữ liệu có thể được so sánh theo những quy tắc khác nhau:

- So sánh String phân biệt hoa/thường: hash có thể dựa trên chính String đó.
- So sánh mã SKU không phân biệt hoa/thường: hash phải dùng cùng dạng chuẩn hóa hoặc một phép băm tương thích với quan hệ không phân biệt hoa/thường.
- So sánh nội dung mảng: dùng **Arrays.equals** trong equals và **Arrays.hashCode** tương ứng trong hashCode.
- So sánh sâu mảng lồng nhau: dùng **Arrays.deepEquals** cùng **Arrays.deepHashCode**.
- So sánh nhiều trường nullable: dùng **Objects.equals** khi cần so sánh và Objects.hash/Objects.hashCode phù hợp khi băm.

**Quy tắc quan trọng:** cùng nghĩa *bằng nhau* thì dữ liệu băm phải cho cùng kết quả. Không nhất thiết phải gọi y hệt phương thức ở cả hai nơi, nhưng cách chuẩn hóa và xử lý giá trị phải tương thích.

### Bước 3: Loại bỏ các trường không tạo nên equality

Không thêm trường phục vụ hiển thị, ghi log, bộ đếm, trạng thái UI, cache, thời điểm truy cập hoặc dữ liệu khác mà equals bỏ qua.

Ví dụ, nếu equals chỉ dùng tenantId và SKU chuẩn hóa:

~~~java
// Sai khi equals không xét displayName:
return Objects.hash(tenantId, normalizedSku, displayName);

// Đúng với tiêu chí equals đã định nghĩa:
return Objects.hash(tenantId, normalizedSku);
~~~

Đây là các đoạn thân phương thức minh họa, không phải chương trình độc lập. Biểu thức đầu có thể làm hai đối tượng equals trả true nhưng hashCode khác nhau chỉ vì displayName khác.

### Bước 4: Chọn thuật toán băm hợp lệ, đủ phân tán

Về tính **đúng**, dùng tập trường phù hợp và giữ ổn định là ưu tiên đầu tiên. Về **hiệu năng**, nên kết hợp các thành phần định danh hợp lý để giảm va chạm, đặc biệt với HashMap/HashSet chứa nhiều phần tử.

Nếu equals so sánh cả id và version, hashCode chỉ trả id.hashCode() có thể vẫn đúng về hợp đồng vì hai đối tượng bằng nhau luôn có cùng id. Tuy vậy, nó bỏ qua version nên nhiều cặp không bằng nhau có thể dồn chung hash, làm phân tán kém. Thực tế thường nên kết hợp cả id và version.

Nói cách khác, **hashCode không bắt buộc phải dùng tất cả trường trong equals**, nhưng tuyệt đối không được phân biệt hai đối tượng mà equals coi là bằng nhau. Dùng đủ các thuộc tính định danh thường là lựa chọn rõ ràng và có phân bố tốt hơn.

### Bước 5: Giữ dữ liệu băm ổn định khi đối tượng nằm trong bộ sưu tập băm

Khi đối tượng được dùng làm khóa HashMap hoặc phần tử HashSet, tránh sửa dữ liệu xác định equality/hash trong suốt thời gian nó nằm trong collection. Nếu thay đổi giá trị đó, collection có thể không tìm lại được khóa vì vị trí lưu ban đầu gắn với hash cũ.

Ưu tiên khóa bất biến: các trường final với kiểu dữ liệu bất biến hoặc bản sao phòng vệ của dữ liệu mutable.

## 4. Ví dụ hoàn chỉnh Java 17+: cùng quan hệ equals thì cùng hash

Quy tắc cho ProductKey: **cùng tenantId và sku không phân biệt chữ hoa/thường** là cùng khóa. Tên hiển thị không tham gia equality. Ví dụ dùng SKU thuộc bộ ký tự ASCII, chuẩn hóa qua Locale.ROOT.

Tạo tệp **HashCodeFieldSelectionDemo.java**:

~~~java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public class HashCodeFieldSelectionDemo {
    public static void main(String[] args) {
        ProductKey a = new ProductKey("shop-1", "ax-7", "Mũ xanh");
        ProductKey b = new ProductKey("shop-1", "AX-7", "Mũ đỏ");
        ProductKey c = new ProductKey("shop-2", "ax-7", "Mũ xanh");

        System.out.println("a equals b: " + a.equals(b));
        System.out.println("a hash equals b hash: "
                + (a.hashCode() == b.hashCode()));
        System.out.println("a equals c: " + a.equals(c));

        Set<ProductKey> set = new HashSet<>();
        set.add(a);
        set.add(b);
        set.add(c);
        System.out.println("HashSet size: " + set.size());

        Map<ProductKey, String> map = new HashMap<>();
        map.put(a, "Đã lưu");
        ProductKey lookup = new ProductKey(
                "shop-1", "aX-7", "Tên hiển thị khác");
        System.out.println("HashMap lookup: " + map.get(lookup));

        System.out.println("Aa hash equals BB hash: "
                + ("Aa".hashCode() == "BB".hashCode()));
        System.out.println("Aa equals BB: " + "Aa".equals("BB"));
    }

    static final class ProductKey {
        private final String tenantId;
        private final String normalizedSku;
        private final String displayName;

        ProductKey(String tenantId, String sku, String displayName) {
            this.tenantId = Objects.requireNonNull(tenantId);
            this.normalizedSku = Objects.requireNonNull(sku)
                    .toUpperCase(Locale.ROOT);
            this.displayName = Objects.requireNonNull(displayName);
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof ProductKey other)) {
                return false;
            }
            return tenantId.equals(other.tenantId)
                    && normalizedSku.equals(other.normalizedSku);
        }

        @Override
        public int hashCode() {
            return Objects.hash(tenantId, normalizedSku);
        }

        @Override
        public String toString() {
            return "ProductKey{" + tenantId + ", "
                    + normalizedSku + ", " + displayName + "}";
        }
    }
}
~~~

Biên dịch và chạy tại thư mục chứa tệp:

~~~bash
javac -encoding UTF-8 HashCodeFieldSelectionDemo.java
java HashCodeFieldSelectionDemo
~~~

Kết quả chuẩn:

~~~text
a equals b: true
a hash equals b hash: true
a equals c: false
HashSet size: 2
HashMap lookup: Đã lưu
Aa hash equals BB hash: true
Aa equals BB: false
~~~

**Vì sao kết quả như trên?**

1. a và b có tenantId cùng là shop-1; sku ax-7 và AX-7 đều được chuẩn hóa thành AX-7. Do đó, equals trả true và hashCode phải giống nhau. Tên hiển thị khác nhau không ảnh hưởng.
2. c thuộc shop-2, nên khác định danh so với a. Vì a và c không bằng nhau, không bắt buộc hash của chúng phải khác.
3. HashSet chứa hai giá trị logic: một cho shop-1/AX-7 và một cho shop-2/AX-7. Thêm b không làm tăng kích thước vì b bằng a.
4. HashMap tra lại khóa bằng một đối tượng mới vẫn tìm được giá trị, dù chuỗi SKU viết kiểu khác và tên hiển thị khác.
5. Hai String "Aa" và "BB" có cùng String.hashCode (2112) nhưng không bằng nhau. Đây là va chạm hợp lệ: hash bằng nhau **không có nghĩa** equals là true.

**Vì sao chọn normalizedSku thay vì sku gốc?** Nếu equals so sánh không phân biệt hoa/thường nhưng hashCode lại gọi hashCode trên chuỗi gốc, hai giá trị như ax-7 và AX-7 có thể có mã băm khác nhau dù equals coi chúng bằng nhau. Chuẩn hóa một lần tại constructor vừa bảo đảm hash và equals dùng cùng giá trị, vừa tránh chạy lại logic trong mỗi lời gọi.

**Vì sao ProductKey là final và các trường là final?** Để minh họa một khóa có trạng thái định danh ổn định. Chuỗi String bất biến; trường final không bị gán lại sau constructor. Tuy nhiên, với kiểu trường là List hoặc mảng thì chỉ final tham chiếu **không ngăn được sửa phần tử bên trong**.

## 5. Các cặp triển khai đúng và sai cần phân biệt

### 5.1. equals bỏ qua một trường, hashCode lại dùng trường ấy

Giả sử equals chỉ so sánh id:

~~~java
@Override
public boolean equals(Object obj) {
    return obj instanceof Item other && id.equals(other.id);
}

// Sai với equals ở trên nếu label có thể khác giữa các Item cùng id.
@Override
public int hashCode() {
    return Objects.hash(id, label);
}
~~~

Hai Item có cùng id nhưng khác label sẽ bằng nhau theo equals, trong khi mã băm có thể khác. Các đoạn trên chỉ minh họa trong lớp có các trường id, label; không phải toàn bộ một lớp độc lập.

Sửa:

~~~java
@Override
public int hashCode() {
    return Objects.hashCode(id);
}
~~~

Nếu id bảo đảm không null, có thể dùng id.hashCode(). Nếu id được phép null thì phải bảo đảm equals xử lý null tương ứng, ví dụ Objects.equals(id, other.id).

### 5.2. equals so sánh hai trường, hashCode chỉ dùng một trường

~~~java
// Trong một lớp mà equals so sánh id và version:
@Override
public int hashCode() {
    return Objects.hashCode(id);
}
~~~

Cách trên **có thể đúng hợp đồng**: khi cả id lẫn version giống nhau thì id đương nhiên giống nhau. Nhưng hai phiên bản khác nhau của cùng id cùng hash, làm tăng va chạm.

Thiết kế có phân bố tốt hơn:

~~~java
@Override
public int hashCode() {
    return Objects.hash(id, version);
}
~~~

Trọng tâm là **tính tương thích với equals**, sau đó mới xét chất lượng phân bố. Không nên diễn giải sai rằng thiếu bất kỳ trường nào của equals trong công thức băm đều tự động vi phạm hợp đồng.

### 5.3. equals bỏ qua kiểu chữ nhưng hashCode dùng chuỗi gốc

~~~java
// equals xác định name bằng equalsIgnoreCase,
// nhưng hashCode dưới đây băm name nguyên gốc:
@Override
public int hashCode() {
    return Objects.hashCode(name); // Có thể vi phạm!
}
~~~

Nếu "ONE" và "one" bằng nhau theo quy tắc equals của lớp, mã băm nguyên gốc của chúng khác nhau. Cách sửa là **thống nhất quy tắc giá trị**. Với mã ASCII không phân biệt hoa/thường, có thể chuẩn hóa bằng toUpperCase(Locale.ROOT) khi tạo đối tượng rồi dùng giá trị chuẩn hóa trong **cả equals và hashCode**.

Với văn bản Unicode, locale hoặc quy tắc so sánh phức tạp, không được tự giả định đổi hoa/thường bằng một bước đơn giản luôn tương đương với mọi phương thức so sánh. Phải định nghĩa phép chuẩn hóa/collation và phép băm tương ứng cùng một quan hệ.

### 5.4. equals dùng nội dung mảng nhưng hashCode dùng định danh mảng

~~~java
// Nếu tags là String[] và hai mảng được coi bằng nhau theo nội dung:
return Arrays.equals(this.tags, other.tags); // Trong equals

// Hash đúng theo nội dung:
return Arrays.hashCode(tags);                 // Trong hashCode
~~~

Các đoạn trên minh họa hai phần cài đặt trong ngữ cảnh đã khai báo tags và other; cần import java.util.Arrays.

Không dùng Objects.hashCode(tags) cho trường hợp này: với mảng thông thường, nó gọi hashCode mặc định của đối tượng mảng, dựa trên định danh tham chiếu, trong khi Arrays.equals so sánh phần tử.

Với mảng lồng nhau, dùng cặp Arrays.deepEquals / Arrays.deepHashCode khi chủ ý so sánh sâu. Với List có equals theo phần tử, List.hashCode cũng được định nghĩa nhất quán theo các phần tử đó; có thể sử dụng Objects.hashCode(list) nếu đó là trường đang xét. Lưu ý phần tử mutable vẫn có thể khiến hash thay đổi.

### 5.5. equals có ngữ nghĩa số đặc biệt

Ví dụ, BigDecimal.equals phân biệt cả giá trị **và scale**: new BigDecimal("1.0") không equals new BigDecimal("1.00"), dù compareTo trả 0.

Nếu một lớp tùy chỉnh định nghĩa equals dựa trên BigDecimal.compareTo(...) == 0, hashCode không được dùng trực tiếp amount.hashCode() vì hai BigDecimal khác scale có thể cho hash khác nhau. Có thể thiết kế dạng chuẩn hóa bằng stripTrailingZeros() rồi dùng dạng đã chuẩn hóa ở cả phép so sánh lẫn phép băm. Khi làm vậy cần xác định rõ cách xử lý null, số 0 và các trường khác. Đừng thay ngữ nghĩa BigDecimal.equals mặc định nếu không có yêu cầu nghiệp vụ cụ thể.

Tương tự với số thực, hãy thống nhất cách xét NaN, +0.0/-0.0 nếu lớp có định nghĩa equals tùy chỉnh. Ưu tiên cặp Double.compare/Double.hashCode hoặc Float.compare/Float.hashCode khi chính cách phân biệt của chúng phù hợp với quan hệ muốn thiết kế.

## 6. Nên dùng Objects.hash, Objects.hashCode hay công thức thủ công?

### Objects.hash(...)

Phù hợp với **nhiều trường**:

~~~java
@Override
public int hashCode() {
    return Objects.hash(tenantId, normalizedSku);
}
~~~

Ưu điểm là ngắn, xử lý trường null và nhất quán với các hash của thành phần. Nó sử dụng cơ chế varargs và băm theo các phần tử, vì vậy trong mã rất nhạy về hiệu năng cần đo đạc thay vì mặc định đó là lựa chọn tối ưu nhất.

### Objects.hashCode(value)

Phù hợp với **một giá trị có thể null**:

~~~java
@Override
public int hashCode() {
    return Objects.hashCode(id);
}
~~~

Nếu id null, kết quả là 0; nếu không null, kết quả là id.hashCode(). Objects.hash(id) **không hoàn toàn tương đương** Objects.hashCode(id), nên hãy dùng công thức có chủ ý và nhất quán với equals. Không trộn lẫn hai cách một cách tùy tiện trong test so sánh hash tuyệt đối.

### Kết hợp thủ công

Với nhiều trường, có thể áp dụng phép kết hợp tuần tự, ví dụ:

~~~java
@Override
public int hashCode() {
    int result = Objects.hashCode(tenantId);
    result = 31 * result + Objects.hashCode(normalizedSku);
    return result;
}
~~~

Đây là minh họa cho lớp có hai trường nói trên. Phép nhân/cộng int có thể overflow, đó là hành vi số nguyên Java xác định được và không khiến công thức băm sai hợp đồng. Công thức không cần tạo mã duy nhất; điều cốt lõi là dữ liệu bằng nhau theo equals cho kết quả băm bằng nhau.

**Không bao giờ dùng** một giá trị ngẫu nhiên, thời gian hệ thống hay bộ đếm tự tăng trong mỗi lần gọi hashCode của đối tượng có trạng thái so sánh không đổi. Cũng không dùng System.identityHashCode(this) để băm lớp có equals theo giá trị: hai đối tượng riêng biệt nhưng bằng nhau có thể nhận identity hash khác nhau.

## 7. Thiết kế khóa mutable và cache hashCode

Nếu trường dùng trong equals bị thay đổi khi đối tượng nằm trong HashMap hoặc HashSet, hashCode có thể đổi theo, làm việc tra cứu hoặc xóa theo khóa trở nên sai kỳ vọng.

Ví dụ về quy trình nguy hiểm:

~~~java
// Minh họa logic, không phải chương trình độc lập:
set.add(key);
key.setId("new-id"); // id được equals và hashCode sử dụng
set.contains(key);    // Không thể dựa vào kết quả để tra cứu như trước
~~~

Không thể chỉ “đóng băng” hashCode trong một cache rồi tiếp tục cho phép id đổi: sau khi trạng thái thay đổi, các đối tượng có cùng id mới theo equals có thể mang hash khác nhau nếu từng cache kết quả cũ. Điều này lại gây vi phạm hợp đồng.

Cách xử lý thực tế:

1. Chọn các trường định danh bất biến khi có thể. Với khóa chứa mảng hoặc List, cân nhắc sao chép phòng vệ và không để lộ cấu trúc mutable.
2. Nếu đối tượng đã nằm trong HashSet/HashMap, hạn chế sửa các trường quyết định equality; nếu bắt buộc đổi định danh, gỡ bằng trạng thái cũ trước khi sửa rồi thêm lại theo trạng thái mới.
3. Chỉ cache hashCode khi mọi dữ liệu ảnh hưởng đến giá trị băm được giữ bất biến trong suốt vòng đời phù hợp của đối tượng. Cache không thay thế hợp đồng equals–hashCode.

Cũng cần cân nhắc đối tượng được truy cập đồng thời: trạng thái mutable cần bảo đảm đồng bộ hoặc thiết kế bất biến; một công thức hashCode đúng trên lý thuyết không tự tạo ra thread safety.

## 8. Kiểm thử để xác nhận chọn trường băm đúng

Đừng chỉ kiểm tra hashCode một lần. Hãy tạo **nhiều đối tượng khác tham chiếu** nhưng bằng nhau theo mọi kịch bản có thể: đổi chữ hoa/thường nếu equality không phân biệt case; thay đổi trường hiển thị bị bỏ qua; thử các giá trị null hợp lệ; thử mảng có nội dung giống nhau; thử lớp con nếu có hệ phân cấp.

Với hai đối tượng a và b có cùng danh tính logic:

~~~java
if (!a.equals(b)) {
    throw new AssertionError("Đầu vào kiểm thử chưa bằng nhau theo equals");
}
if (a.hashCode() != b.hashCode()) {
    throw new AssertionError("Vi phạm hợp đồng equals/hashCode");
}
~~~

Đoạn này chạy trong ngữ cảnh có a và b tương ứng; không phải chương trình đứng riêng. Sau đó kiểm tra hành vi thực tế của HashSet.contains hoặc HashMap.get bằng một đối tượng **mới nhưng bằng nhau**.

Bảng trường hợp nên bao phủ:

| Trường hợp | Điều cần xác nhận |
| --- | --- |
| Cùng các trường định danh, khác displayName | equals true, hash bằng nhau |
| Cùng tenantId, SKU khác cách viết hoa/thường theo quy tắc | equals true, hash bằng nhau |
| Khác tenantId, cùng SKU | equals false; hash có thể trùng |
| Khác SKU và cùng tenantId | equals false; hash có thể trùng |
| Hai String "Aa" và "BB" | hash trùng là hợp lệ, equals false |
| Các giá trị null được hỗ trợ | Không ném NPE; equals/hash thống nhất |
| Dữ liệu so sánh giữ nguyên, gọi hash nhiều lần | Mã băm ổn định |
| Tạo khóa mới bằng khóa đã lưu trong Map | Lấy được giá trị tương ứng |

**Không viết bài test yêu cầu x khác y thì hashCode bắt buộc khác nhau**. Điều đó không phải hợp đồng của Java và sẽ bác bỏ sai các triển khai hợp lệ có collision.

Ngoài ra, hợp đồng equals còn có phản xạ, đối xứng, bắc cầu, nhất quán và so sánh null. Việc chọn đúng các trường trong hashCode không thay thế kiểm tra các điều kiện đó. Nếu dùng kế thừa và một lớp con thêm trường vào equals, cả định nghĩa equality lẫn tập trường băm phải được thiết kế để không phá vỡ quan hệ đối xứng/bắc cầu.

## 9. Checklist khi review hashCode

- **Bắt đầu từ equals:** chính xác những giá trị và quy tắc nào quyết định hai đối tượng bằng nhau?
- **Dùng biểu diễn tương đương:** nếu equals chuẩn hóa, so sánh theo nội dung hay theo quy tắc số riêng, hash cũng cần phản ánh cùng quan hệ.
- **Không thêm dữ liệu ngoài equality** khiến hai đối tượng bằng nhau có hash khác nhau.
- **Ưu tiên dùng đủ dữ liệu định danh** để có phân bố hợp lý, nhưng nhớ không dùng hết trường không tự động làm hash sai hợp đồng.
- **Chọn API đúng kiểu:** Objects.hash cho nhiều trường, Objects.hashCode cho một trường nullable, Arrays.hashCode cho mảng một chiều, Arrays.deepHashCode cho mảng lồng nhau nếu equals so sánh sâu.
- **Bảo đảm ổn định:** tránh dữ liệu ngẫu nhiên, thời gian, identity hash khi equality theo giá trị, hoặc trạng thái mutable của khóa đã lưu.
- **Kiểm tra bằng ví dụ cùng giá trị, khác tham chiếu:** equals true bắt buộc kéo theo hash bằng nhau; false không bắt buộc hash khác.

**Ghi nhớ:** lựa chọn dữ liệu băm đúng là lựa chọn một hàm *không phân biệt hai đối tượng mà equals coi là bằng nhau*. Sự tương thích với equals là điều bắt buộc; chất lượng phân bố, tốc độ và cách cài đặt là những mục tiêu cần tối ưu tiếp theo.