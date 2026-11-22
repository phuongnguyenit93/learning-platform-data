# Đối tượng giá trị và đối tượng có danh tính nghiệp vụ: chọn quan hệ bằng nhau trong Java

## 1. Câu hỏi trước khi viết `equals`: “bằng nhau” theo nghĩa nào?

Trong Java, `==` giữa hai biến tham chiếu cho biết chúng có trỏ đến **cùng một đối tượng** hay không. `equals(Object)` thể hiện **quy tắc bằng nhau về mặt logic** do lớp quyết định. Mặc định, `Object.equals` so sánh theo danh tính tham chiếu, nhưng lớp có thể ghi đè để diễn đạt ý nghĩa của miền nghiệp vụ.

Khi thiết kế mô hình, cần phân biệt hai khái niệm:

- **Value Object (đối tượng giá trị):** điều quan trọng là **giá trị và các thuộc tính có ý nghĩa**; hai thể hiện riêng biệt vẫn được coi là bằng nhau nếu các giá trị thành phần cần so sánh bằng nhau. Ví dụ: tọa độ, khoảng tiền đi kèm đơn vị tiền tệ, khoảng ngày, địa chỉ dùng như một thuộc tính đơn thuần.
- **Entity (thực thể có danh tính nghiệp vụ):** điều quan trọng là **đó có phải cùng một thực thể xuyên suốt vòng đời hay không**; hai bản biểu diễn cùng một thực thể vẫn được xem là bằng nhau khi trạng thái thay đổi. Ví dụ: khách hàng được nhận diện bằng `CustomerId`, đơn hàng bằng `OrderId`.

**Cùng thuộc tính không nhất thiết là cùng entity.** Hai khách hàng tên “Lan” không vì thế mà là một khách hàng. Ngược lại, một khách hàng đổi tên vẫn là chính khách hàng đó.

Đây là quyết định mô hình hóa theo ngữ cảnh. Chẳng hạn một địa chỉ giao hàng chỉ dùng để mô tả vị trí có thể là Value Object; nhưng một điểm giao nhận có mã quản lý, lịch sử và vòng đời riêng có thể là Entity.

## 2. So sánh bản chất và các hệ quả

| Khía cạnh | Value Object | Entity có danh tính nghiệp vụ |
| --- | --- | --- |
| Câu hỏi chính | “Chúng có cùng giá trị không?” | “Chúng có phải cùng thực thể không?” |
| Tiêu chí `equals` | Các thành phần giá trị có ý nghĩa | Định danh ổn định trong phạm vi đã xác định |
| Hai instance riêng biệt | Có thể `equals == true` nếu giá trị giống nhau | Có thể `equals == true` nếu cùng định danh |
| Trạng thái thay đổi | Thường tạo Value Object mới, tránh sửa tại chỗ | Cho phép trạng thái thay đổi mà danh tính giữ nguyên |
| Dữ liệu không nên dùng làm khóa bằng nhau | Trường không thuộc ngữ nghĩa giá trị | Trường thường xuyên đổi như tên, địa chỉ liên hệ, trạng thái |
| Ví dụ | `Address("Lê Lợi", "Đà Nẵng")` | `Customer("C001", "Lan")` |

Trong Java, một **`record`** thường phù hợp để biểu diễn Value Object nhỏ vì nó sinh `equals`, `hashCode` và accessor theo các component. Nhưng record không mặc nhiên đúng mọi quy tắc miền nghiệp vụ và chỉ bất biến ở mức các trường tham chiếu (`final`), **không đảm bảo bất biến sâu** nếu bên trong giữ `List`, mảng hoặc đối tượng có thể sửa.

Entity thường cần một lớp có thuộc tính `id` biểu diễn danh tính ổn định, bên cạnh các thuộc tính trạng thái có thể cập nhật. Không phải mọi đối tượng có trường `id` đều là entity; điều quyết định là ý nghĩa tồn tại và vòng đời của đối tượng trong miền nghiệp vụ.

## 3. Ví dụ Java 17+ có thể biên dịch và chạy

Ví dụ dùng `Address` là Value Object: hai bản địa chỉ có cùng đường và thành phố được coi là bằng nhau. `Customer` là Entity: hai bản có cùng `customerId` biểu diễn cùng khách hàng, dù tên hiển thị khác nhau. Ở đây `customerId` được cấp **trước khi tạo đối tượng**, luôn không rỗng và không thay đổi.

Lưu mã sau trong `ValueVsEntityDemo.java`:

```java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class ValueVsEntityDemo {
    record Address(String street, String city) {
        Address {
            Objects.requireNonNull(street, "street");
            Objects.requireNonNull(city, "city");
        }
    }

    static final class Customer {
        private final String customerId;
        private String displayName;

        Customer(String customerId, String displayName) {
            if (customerId == null || customerId.isBlank()) {
                throw new IllegalArgumentException("customerId must not be blank");
            }
            this.customerId = customerId;
            this.displayName = Objects.requireNonNull(displayName);
        }

        void rename(String name) {
            this.displayName = Objects.requireNonNull(name);
        }

        String displayName() {
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
        Address addressA = new Address("Le Loi", "Da Nang");
        Address addressB = new Address("Le Loi", "Da Nang");
        System.out.println("same address reference: " + (addressA == addressB));
        System.out.println("same address value: " + addressA.equals(addressB));

        Customer customerA = new Customer("C001", "Lan");
        Customer customerB = new Customer("C001", "Lan Nguyen");
        Customer customerC = new Customer("C002", "Lan");
        System.out.println("same customer reference: " + (customerA == customerB));
        System.out.println("same customer identity: " + customerA.equals(customerB));
        System.out.println("different customer identity: " + customerA.equals(customerC));
        System.out.println("different display names: "
                + !customerA.displayName().equals(customerB.displayName()));

        Set<Customer> customers = new HashSet<>();
        customers.add(customerA);
        customerA.rename("Lan Tran");
        System.out.println("found after rename: " + customers.contains(customerA));
        System.out.println("found by same ID: " + customers.contains(customerB));
        System.out.println("equals null: " + customerA.equals(null));
    }
}
```

Chạy trong thư mục chứa tệp:

```bash
javac ValueVsEntityDemo.java
java ValueVsEntityDemo
```

Kết quả:

```text
same address reference: false
same address value: true
same customer reference: false
same customer identity: true
different customer identity: false
different display names: true
found after rename: true
found by same ID: true
equals null: false
```

Ở đây `Address` do `record` tạo ra so sánh từng thành phần; hai lời gọi `new` tạo hai đối tượng riêng nhưng `addressA.equals(addressB)` trả `true`. `Customer` dùng `customerId` trong cả `equals` và `hashCode`: hai đối tượng Java khác nhau đại diện cho khách hàng `C001` vẫn bằng nhau, còn tên chỉ là trạng thái. Việc đổi `displayName` không làm thay đổi mã băm, nên `HashSet` vẫn tìm được đối tượng đã thêm trước khi đổi tên.

## 4. Hợp đồng `equals` và `hashCode` vẫn bắt buộc

Bất kể chọn Value Object hay Entity, triển khai `equals` phải thỏa các nguyên tắc:

1. **Phản xạ:** `x.equals(x)` là `true` với `x` khác `null`.
2. **Đối xứng:** `x.equals(y)` và `y.equals(x)` cho cùng kết quả.
3. **Bắc cầu:** nếu `x.equals(y)` và `y.equals(z)` thì `x.equals(z)`.
4. **Nhất quán:** nếu thông tin dùng để so sánh không đổi thì kết quả không đổi giữa các lần gọi.
5. **So với `null`:** với `x` khác `null`, `x.equals(null)` phải là `false`.

Đặc biệt, nếu `a.equals(b)` là `true`, **bắt buộc** `a.hashCode() == b.hashCode()`. Chiều ngược lại không bắt buộc: hai đối tượng không bằng nhau vẫn có thể cùng mã băm. `HashMap` và `HashSet` dựa trên cả `hashCode` lẫn `equals`, nên sửa một phương thức mà bỏ phương thức còn lại sẽ gây hành vi sai.

Với Value Object, các thành phần tham gia `equals` cũng phải tương thích với `hashCode`. Với Entity, ID dùng để so sánh phải ổn định trong thời gian đối tượng nằm trong cấu trúc băm. Ví dụ trên sử dụng `final customerId` và tránh đưa `displayName` vào hai phương thức.

## 5. Các bẫy phổ biến khi quyết định quan hệ bằng nhau

### 5.1. Dùng trạng thái thay đổi được làm danh tính Entity

Giả sử viết `equals` của `Customer` dựa trên `displayName`. Khi đổi tên, thực thể bỗng “không bằng chính bản cũ”; hai khách hàng trùng tên cũng có nguy cơ bị xem là một. Nếu dùng các trường này để tính `hashCode`, thay đổi tên khi đối tượng đang nằm trong `HashSet`/`HashMap` có thể khiến việc tìm hoặc xóa theo đối tượng thất bại.

Không tự động dùng `email`, số điện thoại, tên đăng nhập hay trạng thái để nhận diện Entity: các dữ liệu này có thể đổi, tái sử dụng hoặc không duy nhất tùy miền nghiệp vụ. Chỉ một **khóa nghiệp vụ thật sự ổn định, duy nhất trong phạm vi xác định** mới phù hợp.

### 5.2. Dùng ID sinh khi lưu database mà bỏ qua vòng đời

Ví dụ một Entity mới tạo có `id == null`, sau khi `INSERT` mới nhận ID từ database. Một mẫu cài đặt sơ sài là `Objects.equals(this.id, other.id)`: nếu không xử lý, **hai Entity mới khác nhau cùng có ID `null`** bị coi là bằng nhau. Ngoài ra, nếu `hashCode()` dựa trên ID thì mã băm thay đổi sau khi lưu, dễ làm hỏng thao tác tìm kiếm trong tập hợp băm.

Có các hướng xử lý tùy kiến trúc: cấp ID bất biến ngay khi tạo Entity (ví dụ UUID do ứng dụng cấp); hoặc nếu ID chỉ có sau khi lưu, xác định rõ quy tắc so sánh Entity chưa lưu (thường chỉ cùng tham chiếu mới bằng nhau), đồng thời giữ `hashCode` phù hợp và ổn định theo vòng đời cần hỗ trợ. Không copy nguyên ví dụ `Customer` ở trên cho một Entity JPA có ID được sinh sau `persist` mà chưa xem lại chiến lược.

**ID kỹ thuật không luôn đồng nghĩa danh tính nghiệp vụ.** Nếu dùng ID database làm tiêu chí, phải xác định phạm vi duy nhất (một bảng, tenant, hệ thống) và việc Entity chưa được lưu, tách/gộp hoặc xuất sang hệ thống khác có làm thay đổi ý nghĩa danh tính hay không.

### 5.3. Dùng `==` để so sánh bản biểu diễn thay vì ý nghĩa

Hai đối tượng `new Customer("C001", ...)` được tạo riêng sẽ cho `a == b` là `false`, dù chúng cùng nhận diện khách hàng `C001` và `a.equals(b)` là `true` theo mô hình này. `==` vẫn hữu ích để so sánh tham chiếu hoặc kiểm tra `null`, nhưng không tự thay được phép so sánh logic.

### 5.4. Value Object chứa cấu trúc mutable hoặc so sánh số tiền sai ngữ nghĩa

`record` không bảo vệ nội dung một component kiểu mảng hoặc danh sách có thể sửa. Nếu phần tử đổi sau khi Value Object đã là khóa `HashMap`, giá trị băm có thể thay đổi. Hãy ưu tiên thành phần bất biến; sao chép phòng vệ với đối tượng mutable, và xác định cách so sánh thích hợp (ví dụ `Arrays.equals` khi nội dung mảng mới là ý nghĩa giá trị).

Với giá trị tiền tệ, không chỉ so sánh số mà quên đơn vị tiền. Ngoài ra, `BigDecimal.equals` phân biệt cả `scale`: `new BigDecimal("1.0").equals(new BigDecimal("1.00"))` là `false`, dù `compareTo` trả `0`. Nếu miền nghiệp vụ coi hai lượng tiền đó là một giá trị, phải định nghĩa và chuẩn hóa quy tắc giá trị nhất quán cho **cả `equals` và `hashCode`**, thay vì sửa mỗi `equals` bằng `compareTo`.

### 5.5. Kế thừa, lớp proxy và phạm vi danh tính

Khi có kế thừa, cách so sánh lớp (`getClass()` hay `instanceof`) ảnh hưởng đến tính đối xứng/bắc cầu và ý nghĩa ID. Không để hai kiểu Entity khác nhau trở thành bằng nhau chỉ vì cùng chuỗi `"C001"` nếu chúng thuộc hai loại danh tính khác nhau. Với ORM/JPA, proxy có thể khiến so sánh lớp trực tiếp cần cân nhắc; quy tắc `equals` phải tương thích với công nghệ ánh xạ và vòng đời Entity thực tế. Ví dụ dùng lớp `Customer final` thuần Java nên không có vấn đề proxy.

## 6. Quy trình chọn `equals` khi thiết kế lớp

1. Hỏi: đối tượng đại diện cho **một giá trị** hay **một thực thể có lịch sử và vòng đời riêng**? Không quyết định chỉ bằng việc nó có ID hay có nhiều trường.
2. Nếu là Value Object, chọn các thành phần tạo nên giá trị; ưu tiên bất biến, cân nhắc dùng `record` khi quy tắc so sánh theo component phù hợp.
3. Nếu là Entity, xác định danh tính duy nhất theo miền nghiệp vụ, phạm vi định danh và thời điểm được cấp; bảo đảm thay đổi trạng thái không làm thay đổi danh tính.
4. Triển khai `equals` và `hashCode` cùng một ngữ nghĩa; xét `null`, lớp con/proxy, đối tượng chưa lưu và việc đặt trong `HashMap`/`HashSet`.
5. Kiểm thử hai instance khác nhau nhưng cùng giá trị/ID, hai instance có dữ liệu giống nhau nhưng khác ID, thay đổi trạng thái, các trường hợp `null` và sự ổn định của mã băm.

**Nguyên tắc sử dụng:** Value Object trả lời “giá trị có giống nhau?”; Entity trả lời “có phải cùng thực thể?”. Thiết kế `equals` theo câu hỏi đúng giúp các tập hợp, cache và quy tắc nghiệp vụ không nhầm trạng thái với danh tính.