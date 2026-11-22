# Không đưa dữ liệu làm phân biệt hai đối tượng đang được coi là bằng nhau vào `hashCode()`

Khi cài đặt `hashCode()`, hãy xuất phát từ **định nghĩa bằng nhau trong `equals(Object)`**. Nếu hai đối tượng được `equals()` coi là bằng nhau, chúng **bắt buộc** trả về cùng một mã băm, ngay cả khi những thuộc tính khác của chúng khác nhau.

Quy tắc trọng tâm:

> Nếu `a.equals(b) == true` thì `a.hashCode() == b.hashCode()` phải đúng.

Đây là yêu cầu một chiều. Hai đối tượng **khác nhau** vẫn có thể trùng mã băm; Java cho phép *hash collision*. Sai lầm là đưa vào `hashCode()` một thuộc tính như tên hiển thị, ghi chú hoặc thời điểm cập nhật có thể **khác giữa các đối tượng mà `equals()` vẫn trả `true`**. Khi đó, `HashSet` và `HashMap` có thể nhận diện sai các đối tượng logic trùng nhau.

## 1. Xuất phát từ quan hệ bằng nhau của đối tượng

Giả sử ứng dụng quản lý khách hàng có:

- `customerId`: mã định danh ổn định của khách hàng.
- `displayName`: tên dùng để hiển thị, có thể chỉnh sửa.

Yêu cầu nghiệp vụ: **hai đối tượng `Customer` cùng `customerId` là cùng một khách hàng**, dù tên hiển thị khác nhau do thông tin được đồng bộ ở thời điểm khác nhau. Do đó:

~~~java
@Override
public boolean equals(Object obj) {
    if (this == obj) {
        return true;
    }
    if (!(obj instanceof Customer other)) {
        return false;
    }
    return customerId.equals(other.customerId);
}
~~~

Đây là **mảnh mã minh họa** nằm trong lớp `Customer`. Phép so sánh chỉ dựa vào `customerId`. Nếu đối tượng A mang mã `"C-01"`, tên `"An"` và đối tượng B mang cùng mã `"C-01"`, tên `"Bình"`, thì `A.equals(B)` phải là `true`.

Một `hashCode()` phù hợp là:

~~~java
@Override
public int hashCode() {
    return customerId.hashCode();
}
~~~

Vì cùng `customerId` thì cùng `customerId.hashCode()`, hai đối tượng được `equals()` coi là bằng nhau chắc chắn nhận mã băm giống nhau.

Không được tự ý bổ sung tên hiển thị vào mã băm:

~~~java
@Override
public int hashCode() {
    return Objects.hash(customerId, displayName); // SAI với equals() đang chỉ so ID.
}
~~~

`Objects.hash(...)` là API hợp lệ; **lỗi nằm ở việc chọn thuộc tính**, không phải ở API. Hai đối tượng cùng ID nhưng tên khác có thể nhận hai mã băm khác nhau, vi phạm hợp đồng bắt buộc.

### Hiểu theo nhóm tương đương

Nếu `equals()` xem tất cả đối tượng có ID `"C-01"` là bằng nhau, ta có một **nhóm tương đương** gồm nhiều bản thể hiện của cùng khách hàng. Hàm `hashCode()` phải có **cùng kết quả cho mọi phần tử của nhóm đó**. Nó có thể ánh xạ nhiều nhóm khác nhau vào cùng một số nguyên, nhưng **không được tách một nhóm bằng nhau thành nhiều mã băm**.

Nói cách khác, mọi dữ liệu ảnh hưởng tới mã băm phải thỏa điều kiện: khi `equals(a, b)` là `true`, phần dữ liệu được dùng phải tạo ra **kết quả băm giống nhau**. Cách dễ kiểm soát nhất là băm cùng khóa bằng nhau mà `equals()` sử dụng.

## 2. Ví dụ Java 17: đúng và sai trong cùng một chương trình

Tạo tệp **`HashCodeEqualityDemo.java`**:

~~~java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class HashCodeEqualityDemo {

    // ĐÚNG: nhận dạng khách hàng bằng customerId.
    static final class Customer {
        private final String customerId;
        private String displayName;

        Customer(String customerId, String displayName) {
            this.customerId = Objects.requireNonNull(customerId);
            this.displayName = Objects.requireNonNull(displayName);
        }

        void rename(String newName) {
            displayName = Objects.requireNonNull(newName);
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof Customer other)) {
                return false;
            }
            return customerId.equals(other.customerId);
        }

        @Override
        public int hashCode() {
            return customerId.hashCode();
        }
    }

    // SAI: equals() chỉ dùng ID nhưng hashCode() dùng cả tên.
    static final class BrokenCustomer {
        private final String customerId;
        private final String displayName;

        BrokenCustomer(String customerId, String displayName) {
            this.customerId = Objects.requireNonNull(customerId);
            this.displayName = Objects.requireNonNull(displayName);
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof BrokenCustomer other)) {
                return false;
            }
            return customerId.equals(other.customerId);
        }

        @Override
        public int hashCode() {
            return 31 * customerId.hashCode() + displayName.hashCode();
        }
    }

    public static void main(String[] args) {
        Customer first = new Customer("C-01", "An");
        Customer sameId = new Customer("C-01", "Binh");

        System.out.println("GOOD equals: " + first.equals(sameId));
        System.out.println("GOOD same hash: "
                + (first.hashCode() == sameId.hashCode()));

        Set<Customer> goodSet = new HashSet<>();
        goodSet.add(first);
        System.out.println("GOOD contains same ID: " + goodSet.contains(sameId));

        first.rename("An moi");
        System.out.println("GOOD contains after rename: "
                + goodSet.contains(first));

        BrokenCustomer badFirst = new BrokenCustomer("C-01", "An");
        BrokenCustomer badSameId = new BrokenCustomer("C-01", "Binh");

        System.out.println("BAD equals: " + badFirst.equals(badSameId));
        System.out.println("BAD same hash: "
                + (badFirst.hashCode() == badSameId.hashCode()));

        Set<BrokenCustomer> badSet = new HashSet<>();
        badSet.add(badFirst);
        System.out.println("BAD contains same ID: "
                + badSet.contains(badSameId));

        badSet.add(badSameId);
        System.out.println("BAD set size: " + badSet.size());
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac HashCodeEqualityDemo.java
java HashCodeEqualityDemo
~~~

**Đầu ra:**

~~~text
GOOD equals: true
GOOD same hash: true
GOOD contains same ID: true
GOOD contains after rename: true
BAD equals: true
BAD same hash: false
BAD contains same ID: false
BAD set size: 2
~~~

**Đọc kết quả:**

1. `first` và `sameId` có cùng `customerId` nên `equals()` là `true`, mặc dù tên hiển thị khác nhau.
2. `Customer.hashCode()` chỉ dựa trên ID, nên hai giá trị hash chắc chắn bằng nhau. `HashSet.contains(sameId)` tìm thấy khách hàng đã thêm.
3. Thay đổi tên hiển thị của `first` **không đổi** `hashCode()` hoặc `equals()` theo định nghĩa ID; việc tra cứu chính phần tử đó trong `HashSet` vẫn hoạt động.
4. Hai `BrokenCustomer` vẫn được `equals()` xem bằng nhau, nhưng công thức hash thêm tên cho ra các kết quả khác nhau với `"An"` và `"Binh"`. Trong ví dụ này, `HashSet` tìm không thấy đối tượng có cùng ID và còn lưu được hai đối tượng mà `equals()` cho là bằng nhau.

Ví dụ sai dùng công thức `31 * id.hashCode() + displayName.hashCode()` để minh họa rõ sự phụ thuộc vào tên; nó không phải khuyến nghị băm tùy biến. Giá trị mã băm cụ thể không phải điều quan trọng; **việc hai đối tượng bằng nhau trả hash khác nhau** mới là vi phạm.

## 3. Tại sao `HashSet` và `HashMap` chịu ảnh hưởng?

Các collection dùng hash tổ chức tra cứu thành hai tầng khái niệm:

1. Chúng dùng mã từ `hashCode()` để xác định nơi cần tìm trong cấu trúc dữ liệu.
2. Trong khu vực tìm kiếm phù hợp, chúng dùng `equals()` để quyết định có phải cùng khóa/phần tử logic hay không.

Nếu `a.equals(b)` là `true` nhưng hai hash khác nhau, quá trình tìm `b` có thể đi theo một vị trí khác nơi `a` đang được lưu, dẫn tới `contains`, `get` hoặc loại trùng hoạt động sai kỳ vọng. Không có bảo đảm rằng `equals()` sẽ “cứu” một mã băm không hợp lệ; collection không có nghĩa vụ quét mọi phần tử để bù cho việc phá hợp đồng.

Ví dụ ở trên cố ý lựa chọn tên khiến hai đối tượng có hash khác nhau và `HashSet` biểu hiện lỗi. Trong chương trình khác, vị trí bucket và kết quả quan sát có thể phụ thuộc giá trị hash hoặc cách cài đặt collection, nhưng **bản thân sự vi phạm hợp đồng vẫn là lỗi trong lớp**, dù một thử nghiệm đơn lẻ tình cờ cho kết quả đúng.

Lưu ý thêm: sau khi đưa đối tượng vào `HashSet` hay làm khóa `HashMap`, **không thay đổi bất kỳ dữ liệu nào tham gia `equals()`/`hashCode()`** trong thời gian nó còn nằm trong cấu trúc đó. Ví dụ tốt sử dụng `customerId` là `final` và không có setter. Chỉ thay đổi `displayName` vốn bị bỏ qua trong cả hai phương thức nên không gây ra lỗi này.

## 4. Quy tắc chọn trường cho `hashCode()`

| Dữ liệu hoặc tình huống | Có nên tham gia mã băm? | Vì sao? |
| --- | --- | --- |
| `customerId` là khóa duy nhất mà `equals()` so sánh | **Có** | Cùng ID thì hash của ID giống nhau |
| `displayName` có thể khác ở hai khách hàng được coi là cùng một người | **Không** | Có thể làm hash khác trong khi `equals()` là `true` |
| `lastUpdated`, ghi chú, trạng thái giao diện bị `equals()` bỏ qua | **Không** | Chúng có thể đổi độc lập với quan hệ bằng nhau |
| Giá trị được suy ra hoàn toàn từ khóa bằng nhau bằng phép tính ổn định | **Có thể**, nhưng thường không cần | Hai đối tượng bằng nhau luôn tạo cùng giá trị suy ra |
| Một trường `equals()` có dùng nhưng không được đưa vào hash | **Có thể hợp lệ** | Hai đối tượng bằng nhau vẫn cho cùng hash; chỉ có thể tăng va chạm |
| Mã băm hằng số như `return 1;` | **Đúng hợp đồng nhưng không hiệu quả** | Mọi đối tượng trùng hash, làm tăng va chạm |

Vì vậy, “dùng đúng các trường trong `equals()`” là **quy tắc thực hành an toàn**, không phải luật bắt buộc phải băm mọi trường được `equals()` so sánh. Luật thật sự là: **bằng nhau thì mã băm phải bằng nhau**. Việc không băm một trường cần thiết để phân biệt đối tượng chỉ tăng khả năng va chạm; còn băm một trường có thể thay đổi giữa các đối tượng bằng nhau sẽ phá hợp đồng.

Ví dụ nếu một `Person` được so sánh bằng cả `countryCode` và `personalNumber`, mã băm chỉ theo `countryCode` vẫn hợp lệ nhưng dễ có nhiều va chạm. Mã băm theo cả hai trường thường phân bố tốt hơn:

~~~java
@Override
public int hashCode() {
    return Objects.hash(countryCode, personalNumber);
}
~~~

Đây là **mảnh mã minh họa**, giả định `equals()` thực sự so cả hai giá trị và hai trường có cách biểu diễn/so sánh nhất quán. Trong trường hợp `Customer` có `equals()` chỉ dùng ID, `Objects.hash(customerId, displayName)` lại không hợp lệ.

## 5. Các trường hợp dễ nhầm khi thiết kế

### A. So sánh không phân biệt hoa thường

Nếu `equals()` coi hai mã `"ab-1"` và `"AB-1"` bằng nhau, nhưng `hashCode()` băm trực tiếp chuỗi nguyên gốc, hợp đồng có thể bị phá. Cần dùng **cùng một dạng khóa chuẩn hóa** ở cả hai phương thức, ví dụ chuyển một mã ASCII được quy định chỉ gồm `A–Z`, `a–z`, chữ số và dấu gạch nối về chữ thường theo `Locale.ROOT` trước khi lưu.

~~~java
import java.util.Locale;

// Minh họa chuẩn hóa khóa trước khi lưu; đã kiểm tra định dạng input ở nơi gọi.
String canonicalId = rawId.toLowerCase(Locale.ROOT);
~~~

Sau đó dùng `canonicalId.equals(...)` và `canonicalId.hashCode()`. Với dữ liệu có quy tắc Unicode/phạm vi ngôn ngữ phức tạp hơn, cần một chính sách chuẩn hóa rõ ràng, nhất quán; chuyển về chữ thường chỉ là ví dụ cho miền mã đơn giản đã được kiểm soát. Tránh trường hợp `equals()` dùng `equalsIgnoreCase` còn hash dùng `String.hashCode()` nguyên gốc.

### B. Mảng và đối tượng lồng nhau

Nếu `equals()` dùng `Arrays.equals(bytesA, bytesB)` để so **nội dung mảng**, không dùng hash dựa trên **danh tính mảng**. Hãy dùng `Arrays.hashCode(bytes)` tương ứng. Tương tự, nếu `equals()` so các trường dữ liệu lồng nhau theo giá trị, `hashCode()` cần dùng cách băm nhất quán với phép bằng nhau đó.

Ví dụ với mảng `byte[] payload` bất biến về nội dung trong vòng đời làm khóa:

~~~java
@Override
public int hashCode() {
    return java.util.Arrays.hashCode(payload);
}
~~~

Đây là mảnh mã riêng, với giả định `equals()` dựa trên `Arrays.equals(payload, other.payload)`. Cần phòng ngừa việc mảng bị sửa bên ngoài, chẳng hạn sao chép phòng vệ ở constructor/getter.

### C. Trường dẫn xuất và dữ liệu cache

Một trường không xuất hiện trực tiếp trong `equals()` **không đương nhiên bị cấm** trong `hashCode()`. Nếu nó được suy ra xác định từ các trường bằng nhau và không đổi khi các trường đó không đổi, dùng nó vẫn có thể đúng. Nhưng đưa cache có thể chưa khởi tạo, thời điểm làm mới hoặc giá trị không đồng nhất giữa hai đối tượng bằng nhau vào công thức hash là nguy hiểm.

Cache chính **kết quả `hashCode()`** là vấn đề khác: nó có thể hợp lệ với một khóa bằng nhau thật sự bất biến và cách khởi tạo an toàn. Không nên dùng cache đó như lý do để bỏ qua hợp đồng hay cho phép khóa bằng nhau thay đổi.

### D. Dữ liệu đổi sau khi đưa vào collection

Có hai lỗi độc lập cần phân biệt:

- **Lỗi quan hệ bằng nhau:** hai đối tượng bằng nhau nhưng `hashCode()` phụ thuộc một trường khác nhau giữa chúng.
- **Lỗi thay đổi khóa:** một đối tượng bị sửa trường dùng trong `equals()`/`hashCode()` sau khi đưa vào `HashSet` hoặc `HashMap`.

Ngay cả khi `equals()` và `hashCode()` được viết hoàn toàn tương ứng, thay đổi các trường khóa trong khi đang dùng làm key vẫn có thể khiến lần tra cứu sau thất bại. Giải pháp phổ biến là dùng khóa bất biến và thay đổi thông tin hiển thị bên ngoài khóa.

## 6. Kiểm thử hợp đồng đúng trọng tâm

Đừng chỉ kiểm tra rằng một đối tượng bằng chính nó. Với lớp `Customer`, các ca quan trọng là:

1. Tạo hai đối tượng **cùng ID, khác tên hiển thị**. Xác nhận `a.equals(b)` và `b.equals(a)` đều `true`; `a.hashCode() == b.hashCode()` cũng phải `true`.
2. Tạo đối tượng **khác ID, cùng tên**. `equals()` phải `false` theo định nghĩa ID. Mã băm được phép bằng hoặc khác; không kiểm thử yêu cầu “khác đối tượng thì hash khác”.
3. Đưa `a` vào `HashSet`, dùng `b` cùng ID để kiểm tra `contains(b)` là `true`.
4. Nếu tên hiển thị có thể sửa, đổi tên và xác nhận phép bằng nhau/hash vẫn không bị ảnh hưởng, bởi vì tên không phải khóa.
5. Kiểm tra `equals(null) == false` và `equals` với một đối tượng không phải `Customer` là `false`.
6. Với ba đối tượng cùng ID, kiểm tra phản xạ, đối xứng và bắc cầu của `equals()`. Sau đó xác nhận hash bằng nhau cho mọi cặp đã được xác nhận bằng nhau.

Không nên viết kiểm thử giả định mọi ID khác đều sinh mã băm khác nhau: trong Java, `hashCode()` trả một `int`, vì vậy va chạm là điều không thể tránh khỏi ở miền dữ liệu đủ lớn. Hãy kiểm thử **bất biến một chiều** và hành vi sử dụng collection.

## 7. Cách ghi nhớ và áp dụng

Khi chuẩn bị ghi đè `hashCode()`, thực hiện theo thứ tự:

1. Xác định **định nghĩa bằng nhau** trước: những trường nào quyết định hai đối tượng thuộc cùng thực thể hoặc cùng giá trị logic?
2. Đảm bảo `equals(Object)` phản ánh chính xác định nghĩa đó và tuân thủ phản xạ, đối xứng, bắc cầu, nhất quán và hành vi với `null`.
3. Tạo mã băm từ những khóa/giá trị **chắc chắn giống nhau khi `equals()` là `true`**.
4. Loại khỏi mã băm các trường chỉ để hiển thị, ghi chú, trạng thái hoặc thông tin có thể khác giữa những đối tượng đã được coi là bằng nhau.
5. Ưu tiên khóa bất biến trong suốt vòng đời sử dụng đối tượng làm key của collection.
6. Viết test cho **hai bản thể hiện khác nhau nhưng cùng giá trị logic**, không chỉ test một tham chiếu so với chính nó.

**Ghi nhớ:** `hashCode()` không phải cách liệt kê mọi thuộc tính của một object. Nó phải tôn trọng cách `equals()` gom các đối tượng thành những nhóm bằng nhau. Băm thêm một trường có thể phân biệt các thành viên trong cùng nhóm là lỗi; cùng nhóm bằng nhau thì phải cùng mã băm, còn khác nhóm vẫn được phép va chạm.