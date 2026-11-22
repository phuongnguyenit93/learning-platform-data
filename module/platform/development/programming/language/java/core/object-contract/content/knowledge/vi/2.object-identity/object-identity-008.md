# Danh tính đối tượng trong bộ nhớ và mã định danh nghiệp vụ trong Java

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt **danh tính đối tượng trong một lần chạy JVM** với **mã định danh của một thực thể trong miền nghiệp vụ**.
- Giải thích đúng vai trò của `==`, `equals()`, `hashCode()` và `System.identityHashCode()`.
- Thiết kế cách so sánh hai đối tượng đại diện cho cùng một thực thể, kể cả khi được tải ở hai lần khác nhau.
- Tránh nhầm địa chỉ bộ nhớ, chuỗi hiển thị đối tượng hoặc mã hash với ID nghiệp vụ; nhận ra các lỗi khi lưu thực thể trong `HashSet`, dùng làm khóa `HashMap` hoặc gán ID sau khi lưu database.

## 2. Hai loại danh tính trả lời hai câu hỏi khác nhau

**Danh tính đối tượng (object/reference identity)** hỏi: “Hai biến tham chiếu có đang trỏ đến **chính cùng một đối tượng** trong JVM hay không?” Với hai tham chiếu đối tượng, biểu thức `a == b` trả lời câu hỏi này. Mỗi lần tạo đối tượng mới bằng `new` thông thường tạo một đối tượng có danh tính riêng, cho dù các trường chứa giá trị giống hệt đối tượng khác. Việc gán `b = a` chỉ tạo thêm tham chiếu đến cùng một đối tượng.

**Mã định danh nghiệp vụ (business identifier)** hỏi: “Hai biểu diễn này có nói đến **cùng một thực thể của hệ thống** hay không?” Ví dụ, hai đối tượng `Customer` có `customerId = "CUS-001"` có thể là hai instance Java khác nhau nhưng đều biểu diễn cùng một khách hàng. ID do ứng dụng hoặc nguồn dữ liệu quy định; nó có thể tồn tại trong database, API, sự kiện và các lần chạy chương trình.

Ví dụ sơ đồ tham chiếu:

```text
a -----+
       +----> Đối tượng Customer #1 { customerId = "CUS-001" }
alias -+

b ----------> Đối tượng Customer #2 { customerId = "CUS-001" }

a == alias         -> true  (cùng một đối tượng)
a == b             -> false (hai đối tượng khác nhau)
a.id().equals(b.id()) -> true (cùng mã nghiệp vụ)
```

Dấu `#1`/`#2` ở sơ đồ chỉ là nhãn minh họa cho hai instance; **không phải** địa chỉ thật, ID hoặc số hash do JVM cung cấp.

| Tiêu chí | Danh tính đối tượng trong JVM | Mã định danh nghiệp vụ |
| --- | --- | --- |
| Điều được nhận diện | Một instance cụ thể trong quá trình thực thi | Một thực thể có ý nghĩa trong miền ứng dụng |
| Cách kiểm tra thường gặp | `a == b` với tham chiếu | So sánh ID theo quy tắc miền, thường qua `equals()` |
| Phạm vi | Một không gian đối tượng của tiến trình JVM | Có thể trải qua database, phiên làm việc, tiến trình và dịch vụ |
| Khi tạo bản sao hoặc tải lại từ database | Tham chiếu khác: `==` thường `false` | Có thể vẫn là cùng thực thể nếu ID giống nhau |
| Khi khởi động lại ứng dụng | Tham chiếu cũ không còn ý nghĩa | ID bền vững có thể tiếp tục nhận diện bản ghi |
| Ai quyết định | Ngữ nghĩa tham chiếu của Java | Thiết kế nghiệp vụ và ràng buộc dữ liệu |
| Tính duy nhất cần hiểu | Không có hai đối tượng khác nhau nào là cùng một tham chiếu tại cùng thời điểm | ID chỉ duy nhất trong **phạm vi được định nghĩa** (ví dụ từng tenant) |

**Lưu ý ngôn từ:** “Danh tính trong bộ nhớ” là cách nói thuận tiện. Java không cung cấp địa chỉ máy thật của mọi đối tượng để lập ID. Bộ gom rác có thể di chuyển đối tượng, trong khi quan hệ `==` giữa các tham chiếu vẫn có cùng ý nghĩa.

## 3. `==`, `equals()` và `hashCode()` không thay thế nhau

### 3.1. Toán tử `==`

- Với **hai tham chiếu**, `==` kiểm tra có cùng đối tượng hay không, bao gồm trường hợp cả hai cùng `null`.
- Với **kiểu nguyên thủy** như `int`, `==` so sánh giá trị nguyên thủy (không có object identity).
- Hai instance khác nhau có cùng dữ liệu vẫn cho `false` khi so tham chiếu bằng `==`. Ngược lại, hai tên biến trỏ cùng instance luôn cho `true`.
- Không dùng `==` để so sánh nội dung `String` hoặc mã ID dạng `String`; dùng `String.equals()` hay `Objects.equals()` nếu có thể có `null`.

### 3.2. Phương thức `equals()`

Lớp `Object` mặc định triển khai `equals()` bằng nhận diện tham chiếu. Lớp con có thể ghi đè để mô tả một quan hệ **bằng nhau theo ngữ nghĩa**:

- **Entity (thực thể):** có thể coi hai object bằng nhau nếu mang cùng một ID ổn định, hợp lệ trong đúng phạm vi nghiệp vụ.
- **Value object (đối tượng giá trị):** thường coi hai object bằng nhau khi các giá trị có ý nghĩa của chúng bằng nhau. Ví dụ, `record Point(int x, int y) {}` tự có `equals()` dựa trên các thành phần `x` và `y`.
- **Không phải mọi class đều nên so sánh bằng ID.** Chỉ ghi đè `equals()` theo business ID khi điều đó đúng với quy tắc nhận diện thực thể của miền.

Một triển khai `equals()` đúng cần giữ các tính chất phản xạ, đối xứng, bắc cầu và nhất quán khi trạng thái liên quan không đổi; so với `null` phải trả về `false`. Việc dùng `final class` trong ví dụ bên dưới giúp tránh các tình huống rắc rối về đối xứng khi có kế thừa.

### 3.3. Phương thức `hashCode()`

Nếu `a.equals(b)` là `true`, **bắt buộc** `a.hashCode() == b.hashCode()`. Chiều ngược lại không đúng: hai đối tượng có cùng mã hash vẫn có thể không bằng nhau vì hash có thể va chạm.

`HashMap` và `HashSet` dựa vào cả `hashCode()` và `equals()`, nên khi thay đổi định nghĩa bằng nhau theo ID phải triển khai `hashCode()` nhất quán. Đặc biệt, **không làm thay đổi các trường tham gia `equals()`/`hashCode()` khi một object đang được dùng làm khóa `HashMap` hoặc nằm trong `HashSet`**; nếu hash thay đổi, việc tìm lại/phát hiện trùng có thể thất bại.

## 4. Ví dụ Java 17+ chạy được

Lớp `Customer` bên dưới nhận diện một khách hàng bằng `customerId` bất biến. Tên hiển thị có thể khác mà không làm thay đổi danh tính nghiệp vụ. Hai `new Customer(...)` là hai instance khác nhau, dù ID trùng nhau.

Lưu vào tệp `IdentityVsBusinessId.java`:

```java
import java.util.HashMap;
import java.util.HashSet;
import java.util.IdentityHashMap;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public class IdentityVsBusinessId {
    static final class Customer {
        private final String customerId;
        private final String displayName;

        Customer(String customerId, String displayName) {
            this.customerId = Objects.requireNonNull(customerId, "customerId");
            this.displayName = Objects.requireNonNull(displayName, "displayName");
        }

        String id() {
            return customerId;
        }

        String name() {
            return displayName;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) return true;
            if (!(other instanceof Customer customer)) return false;
            return customerId.equals(customer.customerId);
        }

        @Override
        public int hashCode() {
            return customerId.hashCode();
        }
    }

    public static void main(String[] args) {
        Customer a = new Customer("CUS-001", "An");
        Customer b = new Customer("CUS-001", "An (bản tải khác)");
        Customer c = new Customer("CUS-002", "An");
        Customer alias = a;

        System.out.println("a == b: " + (a == b));
        System.out.println("a == alias: " + (a == alias));
        System.out.println("a.equals(b): " + a.equals(b));
        System.out.println("a.equals(c): " + a.equals(c));
        System.out.println("Cùng business ID: " + a.id().equals(b.id()));

        Set<Customer> customers = new HashSet<>();
        customers.add(a);
        customers.add(b);
        customers.add(c);
        System.out.println("HashSet size: " + customers.size());

        Map<Customer, String> ordinaryMap = new HashMap<>();
        ordinaryMap.put(a, "Ghi chú của a");
        System.out.println("HashMap get(b): " + ordinaryMap.get(b));

        Map<Customer, String> identityMap = new IdentityHashMap<>();
        identityMap.put(a, "Ghi chú của a");
        System.out.println("IdentityHashMap get(b): " + identityMap.get(b));
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```bash
javac IdentityVsBusinessId.java
java IdentityVsBusinessId
```

Kết quả chuẩn:

```text
a == b: false
a == alias: true
a.equals(b): true
a.equals(c): false
Cùng business ID: true
HashSet size: 2
HashMap get(b): Ghi chú của a
IdentityHashMap get(b): null
```

**Giải thích từng điểm:**

1. `a` và `b` là hai đối tượng do hai lần `new` tạo ra nên `a == b` là `false`, dù cùng ID `CUS-001`. Biến `alias` tham chiếu trực tiếp đến `a` nên `a == alias` là `true`.
2. `Customer.equals()` cố ý so sánh `customerId`. Do đó `a.equals(b)` là `true` và `a.equals(c)` là `false`.
3. `HashSet` chứa hai thực thể khác nhau theo ID (`CUS-001` và `CUS-002`). Nó không thêm `b` thành phần tử thứ ba vì `b.equals(a)` là `true` và hash phù hợp.
4. `HashMap` tìm được giá trị qua khóa `b` vì khóa `b` được xem bằng khóa `a` theo `equals()` và `hashCode()`.
5. `IdentityHashMap` so sánh khóa **theo tham chiếu** (`==`), nên khóa `b` không trùng instance `a` đã thêm; `get(b)` trả về `null`. Đây là cấu trúc đặc biệt hữu ích trong một số thuật toán cần theo dõi instance (ví dụ duyệt đồ thị đối tượng), không phải cách mặc định để lập chỉ mục theo ID nghiệp vụ.

Ví dụ giả định `customerId` luôn được cấp trước khi tạo đối tượng và không thay đổi. Việc hai object cùng ID có tên hiển thị khác là tình huống thường gặp khi dữ liệu được nạp tại thời điểm khác nhau; so sánh entity bằng ID **không đồng nghĩa** các bản sao có trạng thái hoàn toàn giống nhau.

## 5. `System.identityHashCode()` có phải ID trong bộ nhớ không?

`System.identityHashCode(obj)` trả về kiểu `int` là giá trị hash dựa trên danh tính đối tượng, bất kể class đã ghi đè `hashCode()` ra sao. Trong một lần chạy, nhiều lần gọi trên cùng object cho cùng kết quả. Tuy nhiên:

- **Không phải địa chỉ bộ nhớ.** Không thể suy ra địa chỉ thực, vị trí cấp phát hoặc vị trí sau GC từ số hash đó.
- **Không đảm bảo duy nhất.** Hai object khác nhau có thể nhận cùng một giá trị hash do phạm vi `int` hữu hạn và va chạm.
- **Không phải business ID.** Không dùng nó làm khóa database, ID trong HTTP API, mã hóa đơn, ID sự kiện hoặc định danh xuyên lần chạy JVM.
- **Không thay thế `==`.** Để biết hai tham chiếu trỏ cùng object hay không, so trực tiếp `a == b`; so `identityHashCode(a) == identityHashCode(b)` có thể cho kết luận sai nếu hash va chạm.

Tương tự, chuỗi mặc định trông như `SomeClass@1a2b3c` không chứng minh địa chỉ thật hay tính duy nhất. `Object.toString()` mặc định ghép tên class với biểu diễn hex của `hashCode()`; class có thể ghi đè `toString()`/`hashCode()`. Chuỗi log kiểu này chỉ hỗ trợ chẩn đoán ở mức hạn chế và không có ý nghĩa là định danh nghiệp vụ.

## 6. Thiết kế mã định danh nghiệp vụ đúng

### 6.1. Xác định thực thể và phạm vi duy nhất

Ví dụ `orderId` của đơn hàng, `customerId` của khách hàng, hoặc mã đặt chỗ. Trước khi chọn chiến lược ID, cần trả lời:

- ID nhận diện **loại thực thể nào**? Hai `Order` và `Customer` cùng chuỗi `"123"` không trở thành cùng một thực thể.
- ID có duy nhất toàn hệ thống, trong một công ty, hay **chỉ trong một tenant**? Nếu chỉ duy nhất trong tenant, nhận diện có thể cần cặp `(tenantId, localId)`.
- ID được cấp khi tạo entity, khi lưu database hay bởi dịch vụ khác? Có thời điểm entity chưa có ID hợp lệ không?
- ID có ổn định suốt đời thực thể không? Mã hiển thị dễ đổi (số điện thoại, email, tên đăng nhập hoặc số đơn hàng có thể sửa) thường không thích hợp làm danh tính bất biến.
- Nơi nào thực thi quy tắc duy nhất? Cần ràng buộc unique/primary key và xử lý va chạm ở nguồn dữ liệu; riêng `equals()` không thể ngăn hai bản ghi cùng ID phát sinh.

Phân biệt thêm: **database primary key** (ví dụ cột số tăng tự động) và **business key** (ví dụ mã khách hàng mà nghiệp vụ sử dụng) có thể giống hoặc khác nhau. Một surrogate primary key chỉ là khóa kỹ thuật nhưng vẫn có thể được ứng dụng dùng như entity ID bền vững; ngược lại, business key có thể đổi và không phù hợp làm khóa `equals()`. Quyết định dựa trên vòng đời và hợp đồng dữ liệu thực tế.

### 6.2. Ưu tiên ID ổn định khi triển khai equality theo ID

Một cách đơn giản cho domain model thuần Java là cấp ID ngay lúc tạo và giữ `final`, chẳng hạn ID từ dịch vụ phát số hoặc `UUID.randomUUID()` nếu phù hợp yêu cầu. Dùng ID để triển khai `equals()`/`hashCode()` và tránh đưa các thuộc tính có thể thay đổi như tên hoặc trạng thái đơn hàng vào hàm hash của entity. Cách này giúp entity dùng an toàn hơn trong bộ sưu tập băm khi các thuộc tính thông thường thay đổi.

**Trường hợp database tự cấp ID sau khi insert:** entity mới có thể mang `id == null` cho đến lúc lưu. Không được tự động viết `Objects.equals(this.id, other.id)` và kết luận mọi entity chưa lưu đều bằng nhau: hai ID `null` sẽ bị xem là bằng nhau dù là hai thực thể dự kiến độc lập. Cũng không thể tùy tiện thay hash từ giá trị dựa trên `null` sang hash theo ID sau khi object đã được đưa vào `HashSet`/`HashMap`. Hãy định nghĩa rõ chiến lược equality cho trạng thái chưa lưu và đã lưu, dựa trên ràng buộc framework/ORM, vòng đời entity và cách sử dụng collections; hoặc cấp ID ổn định sớm nếu miền nghiệp vụ cho phép.

### 6.3. Không nhầm ID với quyền truy cập hay dữ liệu đồng bộ

- Nhận một `customerId` từ request không có nghĩa người gửi được xem hoặc sửa khách hàng đó. Phải kiểm tra xác thực, quyền và phạm vi tenant riêng.
- Hai object có cùng ID chưa chắc có cùng phiên bản dữ liệu. Sau khi truy xuất lại từ database hay trao đổi giữa dịch vụ, chúng có thể mang trạng thái khác nhau; cần cơ chế đồng bộ, phiên bản hoặc optimistic locking nếu nghiệp vụ đòi hỏi.
- Dù cùng một entity ở database, object Java vừa deserialize từ JSON thường là instance mới. Không dựa vào `==` xuyên API, hàng đợi, JVM, cache phân tán hoặc sau lần khởi động khác.
- Nếu ID là `String`, nên có định dạng/canonicalization rõ ràng: ví dụ phân biệt chữ hoa/thường hay bỏ khoảng trắng là chính sách nghiệp vụ, không phải quy tắc tự phát trong `equals()`.

## 7. Tình huống thực tế và cách chọn phép so sánh

| Tình huống | Câu hỏi đúng | Cách phù hợp |
| --- | --- | --- |
| Hai biến trỏ cùng instance Java? | Có thực sự cùng một object hiện tại? | `a == b` |
| Hai `Customer` được load ở hai transaction có cùng khách hàng? | Có cùng khóa nghiệp vụ hợp lệ? | So ID trong đúng phạm vi hoặc `equals()` đã thiết kế theo entity ID |
| Hai `Money`/`Point` có cùng giá trị? | Có cùng giá trị cấu thành? | `equals()` theo value object; có thể dùng `record` |
| Loại bỏ khách hàng trùng ID trong `HashSet`? | Quy tắc bằng nhau và hash nhất quán? | `equals()` và `hashCode()` theo ID ổn định |
| Theo dõi object đã duyệt để tránh chu trình theo tham chiếu? | Đã gặp đúng instance này? | Có thể dùng `IdentityHashMap` hoặc tập identity phù hợp |
| Ghi log nhận diện object để điều tra? | Muốn liên hệ sự kiện với entity nào? | Log business ID và mã tương quan request/trace khi phù hợp; không dựa vào số identity hash |

Một lỗi điển hình:

```java
Customer first = new Customer("CUS-001", "An");
Customer second = new Customer("CUS-001", "An");
if (first == second) {
    System.out.println("Đã tìm thấy cùng khách hàng");
}
```

Điều kiện ở đây là `false` vì hai instance riêng. Nếu mục tiêu là so khách hàng theo ID đã xác định ổn định, dùng `first.equals(second)` theo class `Customer` ở ví dụ chính, hoặc so trực tiếp `first.id().equals(second.id())`. Đừng thay mọi `==` bằng `equals()` một cách máy móc: việc kiểm tra cùng tham chiếu vẫn đúng khi đó chính là yêu cầu của thuật toán.

## 8. Các ngộ nhận cần tránh

1. **“Cùng dữ liệu thì `==` phải là `true`.”** Sai với tham chiếu: hai object có thể khác danh tính trong JVM nhưng bằng nhau theo giá trị hoặc entity ID.
2. **“`equals()` mặc định so ID.”** Sai: `Object.equals()` mặc định dùng identity. Muốn so ID phải có thiết kế và triển khai cụ thể, nhất quán với `hashCode()`.
3. **“Hash khác nhau mới là hai object khác nhau; hash giống nhau là cùng object.”** Sai: `hashCode()`/`identityHashCode()` đều không phải chứng minh danh tính duy nhất; có va chạm.
4. **“`System.identityHashCode()` là địa chỉ RAM.”** Sai: JVM không cam kết điều này, và GC có thể thay đổi vị trí vật lý.
5. **“Hai bản ghi cùng ID trong database thì cùng một instance Java.”** Sai: ORM, deserialize, hai phiên làm việc hoặc hai tiến trình có thể tạo nhiều instance biểu diễn cùng entity.
6. **“ID chưa cấp đều bằng `null` nên hai entity mới là bằng nhau.”** Sai: entity chưa lưu cần quy tắc riêng; so ID qua `Objects.equals(null, null)` dẫn đến kết luận sai.
7. **“Chỉ cần so ID trong code là dữ liệu đã duy nhất và hợp lệ.”** Sai: cần ràng buộc ở nơi lưu trữ, phạm vi namespace/tenant, kiểm tra quyền và xử lý xung đột.

## 9. Tự kiểm tra

**Câu 1.** `Order x = new Order("O-9")` và `Order y = new Order("O-9")` được tạo bằng hai lần `new`. Giả sử `Order.equals()` được triển khai đúng theo ID bất biến. Kết quả dự kiến của `x == y` và `x.equals(y)` là gì?

**Đáp án:** `false` và `true`. `==` trả lời về cùng instance; `equals()` theo ID trả lời về cùng entity.

**Câu 2.** Hai khách hàng ở tenant `T1` và `T2` có cùng mã nội bộ `"100"`. Có nên so duy nhất chuỗi `"100"` để kết luận cùng khách hàng không?

**Đáp án:** Không, nếu mã chỉ duy nhất trong từng tenant. Cần đưa `tenantId` vào khóa nhận diện hoặc dùng một ID thật sự duy nhất trên toàn hệ thống theo hợp đồng dữ liệu.

**Câu 3.** Một entity được thêm vào `HashSet` lúc `id == null`, sau đó database gán ID và `hashCode()` chuyển từ hash của `null` sang hash của ID mới. Rủi ro là gì?

**Đáp án:** Vị trí bucket theo hash có thể không còn khớp; `contains()`/`remove()` có thể không tìm được object đã thêm. Cần chiến lược equality/hash ổn định phù hợp vòng đời entity.

**Câu 4.** Hai object có `System.identityHashCode()` bằng nhau. Có thể kết luận `a == b` không?

**Đáp án:** Không; hash có thể va chạm. Dùng `a == b` khi câu hỏi là identity của tham chiếu.

---

**Ghi nhớ:** `==` (với reference) nhận diện **cùng object đang tồn tại trong JVM**; business ID nhận diện **cùng thực thể theo quy tắc miền**. `equals()` có thể được thiết kế để phản ánh business ID, và `hashCode()` phải nhất quán với lựa chọn đó. Hai lớp nhận diện này phục vụ các quyết định khác nhau trong ứng dụng Java.