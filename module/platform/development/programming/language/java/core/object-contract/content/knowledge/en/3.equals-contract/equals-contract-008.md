# Chia các đối tượng thành những nhóm có cùng giá trị theo hợp đồng equals

## 1. Bài toán và ý nghĩa của “cùng giá trị”

Cho một tập hoặc danh sách đối tượng Java, ta muốn chia chúng thành các nhóm sao cho **hai đối tượng nằm trong cùng nhóm khi và chỉ khi chúng được xem là bằng nhau theo quy tắc đã chọn**. Đây là phép phân hoạch (partition): mỗi phần tử đầu vào thuộc đúng một nhóm; không bỏ sót, không đưa một phần tử vào hai nhóm. Một nhóm có thể chứa nhiều **instance** khác nhau nhưng có cùng **giá trị logic**.

Trong ngữ cảnh hợp đồng **equals**, quan hệ “cùng giá trị” thường được định nghĩa bằng **a.equals(b)**, không phải **a == b**:

- **==** trên các tham chiếu hỏi chúng có trỏ tới cùng một đối tượng trong bộ nhớ hay không.
- **equals(Object)** hỏi chúng có tương đương về giá trị logic hay không, theo cách lớp đó cài đặt.
- **hashCode()** hỗ trợ tìm kiếm và gom nhóm hiệu quả trong các cấu trúc dựa trên băm như **HashMap**, **LinkedHashMap** và **HashSet**; nó không tự định nghĩa thế nào là bằng nhau.

Ví dụ, hai bản ghi nhân viên khác instance nhưng cùng mã định danh nghiệp vụ có thể thuộc cùng nhóm, nếu lớp quy định **equals** chỉ xét mã nhân viên. Ngược lại, nếu nghiệp vụ coi cả mã và phiên bản là một phần của giá trị, chúng phải nằm ở nhóm khác nhau. **Không tồn tại một cách nhóm “đúng” cho mọi hệ thống**: trước tiên phải xác định chính xác tiêu chí bằng nhau.

### Điều kiện của một phép phân nhóm đúng

Đặt a ~ b khi a.equals(b) là true. Để chia thành những lớp tương đương nhất quán, quan hệ này cần thỏa:

1. **Phản xạ (reflexive):** a.equals(a) luôn true với a khác null.
2. **Đối xứng (symmetric):** nếu a.equals(b) thì b.equals(a).
3. **Bắc cầu (transitive):** nếu a.equals(b) và b.equals(c) thì a.equals(c).
4. **Nhất quán (consistent):** gọi lặp lại cho cùng hai đối tượng phải cho cùng kết quả chừng nào các thông tin dùng để so sánh chưa đổi.
5. **Không bằng null:** a.equals(null) luôn false khi a khác null.

Đây là những điều kiện chính của hợp đồng **Object.equals**. Nếu vi phạm tính đối xứng hoặc bắc cầu, khái niệm “nhóm” sẽ trở nên mâu thuẫn: phần tử có thể thuộc nhóm này khi so với đại diện A nhưng lại thuộc nhóm khác khi so với B. Nếu vi phạm tính nhất quán, kết quả phân nhóm có thể thay đổi ngay trong lúc xử lý.

**Quy tắc đi kèm:** nếu a.equals(b) là true thì a.hashCode() **bắt buộc** bằng b.hashCode(). Hai đối tượng có cùng mã băm **không bắt buộc** bằng nhau (va chạm băm là hợp lệ). Khi khóa không thay đổi về những trường tham gia **equals/hashCode**, giá trị hashCode cũng phải ổn định trong thời gian được dùng làm khóa.

## 2. Chọn đối tượng khóa: nhóm theo equals của phần tử hay theo khóa nghiệp vụ?

Có hai bài toán liên quan nhưng khác nhau:

| Cách nhóm | Tiêu chí cùng nhóm | Khi phù hợp |
| --- | --- | --- |
| Dùng chính đối tượng làm khóa | Hai phần tử có **equals** bằng true | **equals** của lớp đã diễn đạt đúng ý nghĩa “cùng giá trị” |
| Rút ra một khóa bất biến từ phần tử | Hai khóa có **equals** bằng true | Muốn nhóm theo một số trường cụ thể nhưng **không muốn đổi** định nghĩa equals của cả đối tượng |

Ví dụ: đối tượng đơn hàng có thể dùng **equals** theo mã đơn hàng, nhưng báo cáo lại muốn nhóm theo mã khách hàng. Lúc đó phải trích xuất mã khách hàng làm khóa; không sửa **Order.equals** chỉ để phục vụ một báo cáo.

Với khóa HashMap/LinkedHashMap, Java dùng cả **hashCode** lẫn **equals** để xác định khóa tương đương. Khi đưa hai khóa bằng nhau vào map, map giữ **một entry cho nhóm**. Giá trị của entry có thể là **List<T>** lưu đầy đủ mọi phần tử thuộc nhóm, kể cả các phần tử trùng giá trị.

## 3. Ví dụ đầy đủ: phân nhóm theo equals của đối tượng

Giả sử hệ thống quy định **nhân viên có cùng id thì là cùng một nhân viên về mặt logic**. Tên hiển thị không thuộc định danh: tên có thể thay đổi, nhưng các phiên bản mang cùng id cần được nhóm chung.

Tạo tệp **GroupByEqualsDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.stream.Collectors;

public class GroupByEqualsDemo {
    static final class Employee {
        private final String id;
        private final String name;

        Employee(String id, String name) {
            this.id = Objects.requireNonNull(id, "id");
            this.name = Objects.requireNonNull(name, "name");
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof Employee other)) {
                return false;
            }
            return id.equals(other.id);
        }

        @Override
        public int hashCode() {
            return id.hashCode();
        }
    }

    public static void main(String[] args) {
        List<Employee> input = List.of(
            new Employee("E02", "An"),
            new Employee("E01", "Bình"),
            new Employee("E02", "An mới"),
            new Employee("E03", "Chi"),
            new Employee("E01", "Bình mới")
        );

        Map<Employee, List<Employee>> groups = new LinkedHashMap<>();

        for (Employee employee : input) {
            groups.computeIfAbsent(employee, key -> new ArrayList<>())
                  .add(employee);
        }

        for (Map.Entry<Employee, List<Employee>> entry : groups.entrySet()) {
            String names = entry.getValue().stream()
                .map(employee -> employee.name)
                .collect(Collectors.joining(", "));

            System.out.println(entry.getKey().id + " -> [" + names + "]");
        }
    }
}
~~~

Biên dịch và chạy với Java 17 trở lên:

~~~bash
javac GroupByEqualsDemo.java
java GroupByEqualsDemo
~~~

Kết quả chính xác:

~~~text
E02 -> [An, An mới]
E01 -> [Bình, Bình mới]
E03 -> [Chi]
~~~

**Giải thích từng bước:**

1. Hai instance có **id = "E02"** trả về true khi so bằng **equals**, đồng thời có cùng **hashCode**. Chúng trở thành **một khóa logic** trong map.
2. Với nhân viên đầu tiên của một nhóm, **computeIfAbsent** tạo ArrayList mới. Với nhân viên cùng id đến sau, nó trả lại danh sách đã có và thêm phần tử mới.
3. **List<Employee>** lưu **từng lần xuất hiện**, nên nhóm E02 gồm hai đối tượng, không bị mất bản ghi “An mới”.
4. **LinkedHashMap** giữ thứ tự các khóa theo **lần chèn đầu tiên**: E02, rồi E01, rồi E03. Mỗi danh sách giữ thứ tự các phần tử được thêm vào.
5. Đối tượng khóa đại diện của nhóm là lần chèn đầu tiên. Vì vậy, không được tùy tiện hiểu khóa đại diện là bản ghi mới nhất hay bản ghi “chuẩn”; nếu cần chọn bản ghi đại diện theo thời điểm/phiên bản, hãy xử lý quy tắc đó riêng.

**Vì sao cài đặt Employee như trên?** Lớp được khai báo **final** để không phát sinh vấn đề đối xứng do subclass thêm tiêu chí bằng nhau; **id** là **final** và khác null để định danh ổn định. Tên không tham gia cả hai phương thức. Tùy miền nghiệp vụ, có thể cần khóa tổ hợp (ví dụ tenantId + employeeId) nhằm tránh coi hai mã trùng ở hai tenant là một.

### Biến thể bằng Stream

Với danh sách **input** và lớp **Employee** trong ví dụ trên, có thể thay vòng lặp bằng:

~~~java
Map<Employee, List<Employee>> groups = input.stream().collect(
    Collectors.groupingBy(
        employee -> employee,
        LinkedHashMap::new,
        Collectors.toList()
    )
);
~~~

Đây là **đoạn mã thay thế bên trong main**, không phải một chương trình Java độc lập. **groupingBy** lấy chính phần tử làm khóa nên vẫn dựa vào **equals/hashCode** của Employee. Truyền **LinkedHashMap::new** là chủ ý để giữ thứ tự xuất hiện của các nhóm khi chạy stream tuần tự; **Collectors.groupingBy** một tham số không hứa hẹn kiểu map/thứ tự duyệt khóa cụ thể. Danh sách kết quả vẫn chứa tất cả phần tử trong nhóm.

## 4. Ví dụ đầy đủ: nhóm theo khóa giá trị thay vì sửa equals của đối tượng

Giả sử **Customer** là một bản ghi đầy đủ, nhưng báo cáo phải nhóm theo **(tenantId, customerCode)**. Quy tắc nghiệp vụ của báo cáo nói rõ rằng khoảng trắng ngoài cùng và chữ hoa/thường trong **customerCode** không mang ý nghĩa. Ta tạo **CustomerKey** chỉ chứa hai thành phần khóa đã chuẩn hóa, còn Customer giữ nguyên định nghĩa giá trị đầy đủ của record.

Tạo tệp **GroupByBusinessKeyDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

public class GroupByBusinessKeyDemo {
    record Customer(String tenantId, String customerCode, String displayName) {}

    record CustomerKey(String tenantId, String normalizedCode) {}

    public static void main(String[] args) {
        List<Customer> input = List.of(
            new Customer("A", " c123 ", "Lan"),
            new Customer("B", "C123", "Hà"),
            new Customer("A", "C123", "Lan mới"),
            new Customer("A", "x7", "Minh")
        );

        Map<CustomerKey, List<Customer>> groups = new LinkedHashMap<>();

        for (Customer customer : input) {
            String normalized = customer.customerCode()
                .strip()
                .toUpperCase(Locale.ROOT);
            CustomerKey key = new CustomerKey(customer.tenantId(), normalized);

            groups.computeIfAbsent(key, ignored -> new ArrayList<>())
                  .add(customer);
        }

        for (Map.Entry<CustomerKey, List<Customer>> entry : groups.entrySet()) {
            CustomerKey key = entry.getKey();
            System.out.printf("%s/%s -> %d%n",
                key.tenantId(), key.normalizedCode(), entry.getValue().size());
        }
    }
}
~~~

Chạy:

~~~bash
javac GroupByBusinessKeyDemo.java
java GroupByBusinessKeyDemo
~~~

Kết quả:

~~~text
A/C123 -> 2
B/C123 -> 1
A/X7 -> 1
~~~

**Giải thích:** Hai Customer của tenant A có code khác cách viết nhưng sau chuẩn hóa trở thành cùng **CustomerKey("A", "C123")**; khách hàng tenant B vẫn ở nhóm riêng. **record** tự cung cấp equals/hashCode dựa trên **tất cả các component**, nên key tổ hợp ngắn gọn và ít lỗi hơn viết thủ công. Chuẩn hóa chỉ đúng khi nghiệp vụ cho phép; không mặc định đổi chữ hoa/thường cho mọi mã, email, tên hoặc định danh.

Không nên tạo record chứa những trường thay đổi rồi dùng nguyên record đó làm khóa nhóm nếu mục đích chỉ là nhóm theo ID. **record Customer** ở trên có equals theo cả tenantId, customerCode và displayName, nên nhóm theo chính Customer sẽ cho kết quả khác nhóm theo CustomerKey.

## 5. Các cách biểu diễn kết quả và mức độ phù hợp

**Map<K, List<T>>** là biểu diễn thuận tiện nhất cho bài toán giữ toàn bộ thành viên trong từng nhóm: khóa đại diện cho một giá trị logic và list giữ những phần tử tương đương. Có thể dùng **LinkedHashMap** nếu muốn các nhóm được duyệt theo thứ tự xuất hiện, **HashMap** nếu không cần thứ tự, hoặc cấu trúc khác khi yêu cầu thay đổi.

Các biến thể khác phục vụ mục đích khác:

- **Set<T>** (ví dụ **LinkedHashSet**) chỉ giữ một phần tử đại diện cho mỗi giá trị logic, hữu ích để loại trùng. Nó **không giữ danh sách đầy đủ** các phần tử của nhóm.
- **Map<K, Long>** hoặc **Map<K, Integer>** đếm tần suất theo từng giá trị khóa, nhưng không giữ các đối tượng thành viên.
- **List<List<T>>** giữ từng nhóm mà không cần đối tượng khóa map; có thể xây bằng cách so phần tử với đại diện mỗi nhóm. Cách quét tuyến tính này thường tốn **O(n²)** phép so sánh ở trường hợp xấu, trong khi gom nhóm bằng hash map thường gần **O(n)** trung bình nếu hash phân phối tốt.
- **TreeMap** hoặc **TreeSet** xác định trùng khóa theo **Comparator.compare(a, b) == 0** hay **compareTo(a, b) == 0**, không trực tiếp theo equals. Nếu comparator không nhất quán với equals, kết quả nhóm có thể khác nhóm theo hợp đồng equals. Chỉ dùng khi đó chính là quy tắc mong muốn.

Nếu chọn **Map<K, List<T>>**, cần quyết định rõ liệu output phải giữ **thứ tự đầu vào**, **thứ tự sắp xếp theo khóa**, hay không quan tâm thứ tự. Bản thân việc hai đối tượng bằng nhau không hàm ý một thứ tự cụ thể.

## 6. Lỗi thường gặp và vì sao nhóm bị sai

### 6.1. Override equals nhưng quên hashCode

~~~java
@Override
public boolean equals(Object obj) {
    // Logic so sánh theo id
    // (chỉ minh họa lỗi thiết kế, không phải chương trình độc lập)
}
~~~

Đây là **minh họa bằng chú thích**, không phải hàm có thể biên dịch: nếu lớp override equals theo id nhưng để hashCode kế thừa từ Object, hai đối tượng bằng nhau có thể có mã băm khác nhau. **HashMap/HashSet** có thể lưu chúng ở các vị trí khác nhau và tạo ra **hai nhóm sai**. Luôn override **equals** và **hashCode** cùng nhau, dùng cùng tập thuộc tính định danh.

### 6.2. Dùng == để kiểm tra giá trị của object

Hai object độc lập **new Employee("E02", ...)** thường có tham chiếu khác nhau. **==** trả false cho hai tham chiếu đó dù equals trả true. Với String và các wrapper, hiện tượng cache/intern càng khiến dùng == có vẻ “thỉnh thoảng đúng”, vì vậy phải dùng đúng phép so sánh theo ý nghĩa mong muốn.

### 6.3. Dùng trường có thể thay đổi làm khóa hash

Nếu id (hoặc một component tham gia hashCode) thay đổi **sau khi** đã chèn đối tượng vào HashMap, entry vẫn nằm ở vị trí tổ chức theo hash cũ; tra cứu/gom nhóm sau đó có thể thất bại hoặc bất nhất. Nên ưu tiên **khóa bất biến** (record key, String ID không đổi, final fields); nếu cần đổi định danh, xây lại map bằng khóa mới.

### 6.4. Chỉ dựa vào hashCode để kết luận bằng nhau

**a.hashCode() == b.hashCode()** không đủ chứng minh **a.equals(b)**. Va chạm hash xảy ra hợp lệ, và HashMap vẫn gọi equals để phân biệt các khóa có cùng hash.

### 6.5. Nhầm equals với compareTo / Comparator

~~~java
new java.math.BigDecimal("1.0").equals(
    new java.math.BigDecimal("1.00"))  // false
~~~

Với BigDecimal, **compareTo** cho kết quả 0 giữa hai giá trị này nhưng **equals** trả false vì scale khác nhau. Vì thế nhóm bằng **HashMap<BigDecimal, ...>** có thể tách chúng; nhóm bằng **TreeMap** theo thứ tự tự nhiên có thể gộp chúng. Nếu nghiệp vụ chỉ xét giá trị số, cần quyết định và biểu diễn khóa được chuẩn hóa một cách nhất quán, chẳng hạn cân nhắc **stripTrailingZeros()** cùng cách xử lý giá trị zero và giới hạn miền dữ liệu.

### 6.6. Nhầm equals của array với equals theo phần tử

Mảng không override Object.equals để so nội dung: **new int[]{1,2}.equals(new int[]{1,2})** là false. Nếu khóa là mảng, muốn so giá trị theo phần tử phải dùng **Arrays.equals** (mảng một chiều) hoặc **Arrays.deepEquals** (mảng lồng nhau), đồng thời xây khóa có **hashCode** tương thích (Arrays.hashCode/deepHashCode). Cách thuận tiện khác là chuyển về cấu trúc giá trị bất biến thích hợp.

### 6.7. Dùng quan hệ “gần giống” nhưng không bắc cầu

Ví dụ quy tắc **|a - b| < 2** cho các số 1, 2, 3: 1 gần 2 và 2 gần 3, nhưng 1 không gần 3. Đây không phải quan hệ tương đương; không nên đưa trực tiếp vào **equals** để gom nhóm theo từng lớp tương đương. Bài toán phân cụm theo khoảng cách/độ gần phải dùng thuật toán và quy tắc nhóm riêng.

### 6.8. Cạm bẫy với null, entity và kế thừa

- **a.equals(null)** phải false; nếu a có thể null thì không được gọi trực tiếp **a.equals(...)**. Có thể dùng **Objects.equals(a, b)** để so sánh null-safe. **List.of** không cho phép phần tử null; **Collectors.groupingBy** của JDK từ chối khóa phân nhóm null. Nếu dữ liệu có null, cần đặt chính sách loại bỏ, tách riêng hay dùng sentinel có ý nghĩa.
- Các entity có ID được tạo sau khi lưu (ví dụ entity chưa persisted) không nên tự động coi mọi ID null là cùng một giá trị: nhiều entity mới có thể là các thực thể khác nhau. Cần thiết kế equals/hashCode đúng vòng đời định danh.
- So sánh giữa lớp cha và lớp con có thêm trạng thái dễ làm hỏng đối xứng hoặc bắc cầu; cân nhắc lớp final, record, hoặc quy tắc kế thừa được thiết kế chặt chẽ.

## 7. Kiểm chứng hợp đồng trước khi tin kết quả nhóm

Với mỗi mẫu **a, b, c**, hãy kiểm tra bằng ví dụ cụ thể:

1. **a.equals(a)** là true; **a.equals(null)** là false.
2. **a.equals(b)** đúng bằng **b.equals(a)**.
3. Nếu **a.equals(b)** và **b.equals(c)** đều true, thì **a.equals(c)** cũng true.
4. Nếu **a.equals(b)** là true, **a.hashCode() == b.hashCode()** cũng phải true.
5. Nếu **a** và **b** được coi là khác giá trị, phép nhóm tạo hai nhóm riêng khi cần; nếu bằng nhau, chúng phải ở cùng một nhóm.
6. Thêm phần tử trùng hoặc xáo thứ tự đầu vào không được làm thay đổi **quan hệ thành viên cùng nhóm**; nếu dùng LinkedHashMap thì thứ tự hiển thị nhóm có thể đổi theo thứ tự xuất hiện.
7. Tổng số **phần tử trong tất cả danh sách nhóm** phải bằng số phần tử đầu vào đã được giữ lại sau chính sách lọc; số nhóm phải bằng số giá trị khóa phân biệt.

Có thể thử thêm ba instance với cùng khóa logic, các khóa có hash collision, khóa ở hai tenant khác nhau, null, và các giá trị được chuẩn hóa. Trong kiểm thử tự động, sử dụng các assertion rõ ràng hoặc thư viện kiểm tra equals/hashCode nếu dự án đã có. Một vài ví dụ chạy đúng không chứng minh đầy đủ hợp đồng với mọi đầu vào, nhưng giúp phát hiện nhiều lỗi thiết kế phổ biến.

## 8. Quy trình áp dụng vào dữ liệu thật

1. **Viết rõ định nghĩa “cùng giá trị”** của trường hợp nghiệp vụ: cùng ID, cùng tổ hợp tenant + ID, hay trùng toàn bộ giá trị.
2. **Chọn khóa:** dùng chính đối tượng nếu equals của lớp phù hợp; nếu không, trích xuất khóa bất biến chuyên biệt. Đảm bảo equals/hashCode của khóa tuân hợp đồng.
3. **Chuẩn hóa có chủ đích**, trước khi gom nhóm và chỉ đối với những khác biệt nghiệp vụ muốn bỏ qua (ví dụ khoảng trắng bao ngoài, cách viết hoa/thường).
4. **Chọn dạng kết quả:** danh sách thành viên, số lần xuất hiện hay chỉ tập giá trị duy nhất; chọn cấu trúc map/set phù hợp với yêu cầu thứ tự.
5. **Thực hiện phân nhóm và kiểm tra:** mỗi phần tử vào đúng một nhóm; không thất lạc phần tử, không gộp nhầm các khóa khác nhau; đặc biệt kiểm chứng khóa null và khóa biến đổi.
6. **Giữ hợp đồng ổn định trong thời gian dùng khóa:** không thay đổi trường định danh của khóa khi đang lưu trong map.

**Ghi nhớ:** khả năng chia đối tượng thành các nhóm cùng giá trị dựa trên **một quan hệ tương đương hợp lệ**. Trong cấu trúc hash, **equals quyết định bằng nhau** và **hashCode phải nhất quán với equals**. Khi yêu cầu nhóm chỉ theo một phần dữ liệu, hãy thiết kế **khóa giá trị riêng** thay vì làm sai ý nghĩa equals của đối tượng gốc.
