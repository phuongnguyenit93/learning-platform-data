# Quy tắc equals và hashCode khi danh tính liên quan đến lưu trữ

Trong Domain-Driven Design (DDD), **Entity** được nhận diện bởi danh tính xuyên suốt vòng đời, không phải bởi toàn bộ thuộc tính tại một thời điểm. Hai đối tượng có thể có cùng tên, địa chỉ hoặc trạng thái nhưng vẫn là hai Entity khác nhau. Ngược lại, một Entity vẫn là cùng một đối tượng nghiệp vụ dù các thuộc tính của nó thay đổi.

Trong Java, danh tính này thường được thể hiện qua hai phương thức **equals()** và **hashCode()**. Khi Entity được lưu bằng ORM hoặc có định danh do cơ sở dữ liệu sinh ra, việc cài đặt hai phương thức này cần tính đến cả vòng đời trước và sau khi lưu. Một cách cài đặt tưởng như hợp lý có thể làm hỏng hành vi của HashSet, HashMap, quan hệ Entity hoặc kiểm thử khi ID được gán muộn.

Bài học này giải thích hợp đồng của equals/hashCode, phân biệt danh tính nghiệp vụ với khóa lưu trữ, phân tích các lựa chọn khi ID được sinh bởi ứng dụng hoặc cơ sở dữ liệu, và trình bày những lưu ý khi Entity làm việc với ORM, proxy và collection.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao Entity được so sánh theo danh tính thay vì toàn bộ thuộc tính.
- Nêu các yêu cầu của hợp đồng equals/hashCode trong Java.
- Phân biệt business identity, persistence identity và database primary key.
- Nhận biết lỗi khi hashCode phụ thuộc vào ID được gán sau khi persist.
- Chọn giữa khóa nghiệp vụ bất biến và khóa lưu trữ làm cơ sở so sánh.
- Thiết kế equals/hashCode phù hợp với Entity có trạng thái transient, persistent và detached.
- Nhận diện rủi ro từ ORM proxy, kế thừa, association, Lombok và collection.
- Viết kiểm thử cho hành vi bình đẳng trước và sau khi lưu.

## 1. Entity được nhận diện bằng danh tính

Entity là đối tượng miền có định danh riêng và vòng đời. Hai Entity có thể có cùng các thuộc tính nhưng vẫn đại diện cho hai đối tượng khác nhau.

Ví dụ, hai khách hàng có cùng tên và địa chỉ vẫn có thể là hai người khác nhau. Một khách hàng đổi địa chỉ hoặc số điện thoại vẫn là cùng khách hàng đó. Tương tự, hai đơn hàng có cùng danh sách sản phẩm và tổng tiền vẫn là hai đơn hàng riêng nếu chúng có mã định danh khác nhau.

| Câu hỏi | Entity | Value Object |
| --- | --- | --- |
| Điều gì xác định sự đồng nhất? | Danh tính | Giá trị các thuộc tính |
| Thuộc tính có thể thay đổi mà vẫn là cùng đối tượng? | Có | Giá trị thay đổi tạo ra một giá trị khác |
| Ví dụ | Customer, Order, Shipment | Money, Address, DateRange |
| So sánh điển hình | Cùng identity trong phạm vi mô hình | Các thành phần giá trị bằng nhau |

Với Value Object, so sánh tất cả thành phần có ý nghĩa thường phù hợp. Với Entity, so sánh mọi thuộc tính là sai trong nhiều trường hợp: một thay đổi địa chỉ không nên làm khách hàng trở thành một người khác.

### Danh tính trong một Bounded Context

Danh tính Entity có ý nghĩa trong phạm vi mô hình. Một Customer trong Sales Context và một Customer trong Billing Context có thể đại diện cho cùng một con người ngoài đời nhưng mang trách nhiệm, dữ liệu và vòng đời khác nhau. Không nên giả định hai Entity thuộc hai Bounded Context là cùng một đối tượng miền chỉ vì chúng có cùng chuỗi ID.

Khi so sánh Entity, cần xác định rõ loại Entity và phạm vi identity. Trong một ứng dụng, kiểu lớp có thể giúp phân biệt các loại đối tượng. Khi trao đổi qua context, hợp đồng tích hợp cần chỉ rõ ID thuộc hệ thống hoặc phạm vi nào.

## 2. Hợp đồng equals() và hashCode() của Java

Java quy định một số đặc tính cho equals():

1. **Phản xạ (reflexive):** một đối tượng phải bằng chính nó.
2. **Đối xứng (symmetric):** nếu A bằng B thì B phải bằng A.
3. **Bắc cầu (transitive):** nếu A bằng B và B bằng C thì A phải bằng C.
4. **Nhất quán (consistent):** kết quả không được thay đổi giữa các lần gọi nếu thông tin dùng để so sánh không thay đổi.
5. **So sánh với null:** mọi đối tượng khác null phải trả về false khi so với null.

Hợp đồng của hashCode():

- Nếu hai đối tượng bằng nhau theo equals(), chúng phải có cùng hashCode().
- Hai đối tượng không bằng nhau có thể có cùng hashCode(); hash code không phải định danh duy nhất.
- Hash code nên ổn định trong thời gian thông tin dùng để tính hash không thay đổi.

HashSet và HashMap sử dụng hashCode() để chọn vùng lưu trữ trước, sau đó dùng equals() để xác định phần tử có bằng nhau hay không. Vì vậy, nếu hai đối tượng bằng nhau nhưng có hash code khác nhau, collection có thể chứa cả hai. Nếu hash code của một đối tượng thay đổi sau khi nó đã được thêm vào collection, collection có thể không tìm thấy đối tượng ở vị trí cũ.

### equals() và hashCode() phải được thiết kế cùng nhau

Không nên chỉ viết equals() rồi để hashCode() mặc định từ Object. Mặc định của Object thường dựa trên identity của instance trong bộ nhớ, trong khi equals() có thể được viết để so sánh ID lưu trữ. Khi đó hai đối tượng có cùng ID có thể equals() là true nhưng hashCode() khác nhau, vi phạm hợp đồng.

Ngược lại, hai đối tượng có hashCode() giống nhau không có nghĩa chúng bằng nhau. Va chạm hash là hợp lệ; equals() mới là phép kiểm tra bình đẳng cuối cùng.

## 3. Ba loại danh tính cần phân biệt

Khi Entity liên quan đến lưu trữ, thường có ba khái niệm dễ bị trộn lẫn:

- **Business identity:** danh tính theo nghiệp vụ, được chuyên gia dùng để nhận diện đối tượng.
- **Persistence identity:** định danh được persistence mechanism dùng để nhận biết một bản ghi hoặc Entity đã được quản lý.
- **Database primary key:** khóa chính trong lược đồ lưu trữ.

Ba loại này có thể trùng nhau nhưng không bắt buộc.

Ví dụ, khách hàng có mã thành viên **CUS-2026-015** được dùng trong nghiệp vụ. Cơ sở dữ liệu có thể lưu khách hàng bằng khóa số **48291**. Mã thành viên là business identity; khóa số là primary key. Một hệ thống khác có thể dùng UUID làm persistence identity trong khi vẫn hiển thị mã thành viên.

| Loại danh tính | Ví dụ | Câu hỏi cần trả lời |
| --- | --- | --- |
| Business identity | Mã khách hàng, mã hợp đồng, số đơn theo nghiệp vụ | Người làm nghiệp vụ nhận diện đối tượng bằng gì? |
| Persistence identity | ID mà ORM dùng để quản lý Entity | Persistence context phân biệt Entity bằng gì? |
| Database primary key | Cột khóa chính trong bảng | Cơ sở dữ liệu định danh dòng dữ liệu bằng gì? |

Nếu khóa nghiệp vụ thực sự duy nhất, ổn định và không thay đổi, nó có thể là cơ sở tốt cho equals/hashCode. Nếu khóa nghiệp vụ có thể đổi hoặc chỉ duy nhất trong một phạm vi chưa được biểu diễn, dùng nó trực tiếp có thể gây lỗi.

## 4. Vấn đề khi ID được cơ sở dữ liệu sinh sau khi lưu

Nhiều ORM hỗ trợ ID sinh tự động, chẳng hạn sequence, identity hoặc generated value. Khi một Entity vừa được tạo trong bộ nhớ nhưng chưa persist, ID có thể là null. Sau khi persist hoặc flush, cơ sở dữ liệu hoặc ORM mới gán ID.

Ví dụ:

```java
Customer first = new Customer();
Customer second = new Customer();

System.out.println(first.getId());  // null
System.out.println(second.getId()); // null
```

Nếu equals() chỉ so sánh ID bằng cách dùng Objects.equals(id, other.id), hai Entity mới có ID null sẽ bị xem là bằng nhau. Điều này sai: hai khách hàng mới tạo là hai Entity khác nhau, dù chưa có khóa lưu trữ.

Một lỗi khác xuất hiện nếu hashCode() được tính trực tiếp từ ID:

```java
@Override
public int hashCode() {
    return Objects.hash(id);
}
```

Trước khi persist, hash code được tính từ null. Sau khi lưu, ID được gán, hash code thay đổi. Nếu Entity đã nằm trong HashSet hoặc được dùng làm khóa HashMap, collection có thể không tìm thấy nó nữa.

### Ví dụ lỗi với HashSet

```java
Set<Customer> customers = new HashSet<>();

Customer customer = new Customer();
customers.add(customer);

// ORM lưu Entity và gán id = 100.
customer.assignGeneratedId(100L);

boolean found = customers.contains(customer);
```

Nếu hashCode() phụ thuộc vào ID vừa thay đổi, contains() có thể trả về false vì HashSet tìm ở bucket mới trong khi đối tượng vẫn nằm ở bucket cũ.

Vấn đề không nằm ở HashSet. Vấn đề là thuộc tính dùng để tính hash đã thay đổi trong lúc đối tượng đang được collection quản lý.

## 5. Các chiến lược lựa chọn equality

Không có một cách cài đặt duy nhất phù hợp với mọi Entity. Hãy xác định ID được tạo khi nào, có ổn định không, có khóa nghiệp vụ tự nhiên không và ORM có sử dụng proxy hoặc kế thừa không.

### Chiến lược A: dùng khóa nghiệp vụ bất biến

Nếu Entity có một business key thỏa mãn các điều kiện sau, có thể dùng nó cho equals/hashCode:

- Duy nhất trong phạm vi nghiệp vụ đã xác định.
- Được gán ngay khi tạo Entity.
- Không thay đổi trong suốt vòng đời.
- Có thể xác định mà không cần tải association hoặc truy vấn database.

Ví dụ, một hợp đồng có mã hợp đồng duy nhất do hệ thống nghiệp vụ cấp và không bao giờ đổi. Khóa đó có thể là cơ sở so sánh.

```java
public final class Contract {
    private final ContractNumber number;

    public Contract(ContractNumber number) {
        this.number = Objects.requireNonNull(number);
    }

    @Override
    public boolean equals(Object obj) {
        if (this == obj) {
            return true;
        }
        if (!(obj instanceof Contract other)) {
            return false;
        }
        return number.equals(other.number);
    }

    @Override
    public int hashCode() {
        return number.hashCode();
    }
}
```

Ở ví dụ này, ContractNumber phải là Value Object bất biến và được bảo đảm duy nhất trong phạm vi Contract. Nếu mã hợp đồng chỉ duy nhất theo từng chi nhánh, equality cần bao gồm cả chi nhánh hoặc một phạm vi định danh tương đương.

Không phải mọi trường có vẻ duy nhất đều là business key tốt. Email khách hàng có thể thay đổi, được chia sẻ hoặc được cập nhật theo chính sách; tên và số điện thoại càng không phù hợp làm danh tính. Một giá trị có unique constraint ở database vẫn cần kiểm tra xem nó có bất biến theo nghiệp vụ hay không.

### Chiến lược B: dùng ID được gán trước khi persist

Một số hệ thống tạo UUID, ULID hoặc ID khác ngay trong ứng dụng trước khi lưu. Khi ID được gán lúc tạo Entity và không thay đổi, có thể dùng ID đó cho cả equals() và hashCode().

```java
public final class Shipment {
    private final UUID id;

    public Shipment() {
        this.id = UUID.randomUUID();
    }

    public UUID getId() {
        return id;
    }

    @Override
    public boolean equals(Object obj) {
        if (this == obj) {
            return true;
        }
        if (!(obj instanceof Shipment other)) {
            return false;
        }
        return id.equals(other.id);
    }

    @Override
    public int hashCode() {
        return id.hashCode();
    }
}
```

Vì ID không đổi sau khi tạo, hash code ổn định trước và sau persist. Tuy nhiên, cần bảo đảm ID thực sự duy nhất theo phạm vi Entity và không bị thay đổi bởi ORM hoặc logic ứng dụng.

### Chiến lược C: dùng database-generated ID và hash code ổn định

Nếu ID chỉ được gán khi persist, một chiến lược thường dùng là:

- Hai reference cùng trỏ đến một instance thì bằng nhau.
- Hai Entity khác instance chỉ bằng nhau khi cả hai có ID khác null và ID bằng nhau.
- Entity chưa có ID không bằng một Entity transient khác.
- hashCode() dùng một giá trị ổn định theo lớp Entity thay vì ID có thể thay đổi.

Ví dụ đơn giản cho Entity không có kế thừa:

```java
public class Customer {
    private Long id;

    protected Customer() {
        // Constructor dành cho persistence provider.
    }

    public Long getId() {
        return id;
    }

    @Override
    public boolean equals(Object obj) {
        if (this == obj) {
            return true;
        }
        if (!(obj instanceof Customer other)) {
            return false;
        }

        Long thisId = getId();
        return thisId != null && thisId.equals(other.getId());
    }

    @Override
    public int hashCode() {
        return Customer.class.hashCode();
    }
}
```

Trong ví dụ, hai Customer transient khác nhau không bằng nhau vì ID của chúng đều null. Khi một Customer đã được lưu và một bản Entity khác được tải từ cùng bản ghi, chúng có thể bằng nhau vì cùng ID. hashCode() không đổi khi ORM gán ID nên collection không mất khả năng tìm kiếm phần tử.

Hash code cố định theo lớp có thể làm nhiều phần tử rơi vào cùng bucket, giảm hiệu năng của HashSet/HashMap khi collection rất lớn. Đây là một đánh đổi: tính đúng đắn của hash collection quan trọng hơn việc phân bố hash hoàn hảo khi ID chỉ xuất hiện sau persist. Nếu hệ thống có thể cấp ID ổn định trước khi lưu hoặc dùng business key bất biến, các lựa chọn đó có thể tránh đánh đổi này.

Ví dụ trên giả định Customer không có hierarchy Entity. Với inheritance, cần quyết định rõ hai lớp con khác nhau có thể bằng nhau hay không. Không được để hai loại Entity khác nhau vô tình bằng nhau chỉ vì ID số trùng nhau.

## 6. Lưu ý khi dùng ORM proxy và kế thừa

ORM có thể tạo proxy để trì hoãn việc tải dữ liệu. Proxy thường là lớp con được sinh động, vì vậy phép so sánh lớp bằng getClass() có thể cho kết quả khác giữa Entity thật và proxy đại diện cho cùng Entity.

Ví dụ, nếu equals() dùng:

```java
if (getClass() != obj.getClass()) {
    return false;
}
```

Một đối tượng Customer thật và một proxy Customer có thể bị xem là khác lớp dù chúng đại diện cho cùng một Entity. Tuy nhiên, thay bằng instanceof một cách máy móc cũng có rủi ro nếu mô hình có kế thừa: Customer và VipCustomer có thể bị xem là bằng nhau chỉ vì cùng ID.

### Chọn chính sách theo mô hình kế thừa

Trước khi triển khai equals(), hãy trả lời:

- Các lớp con có phải là những loại Entity khác nhau về danh tính không?
- Một Entity ở lớp cha có thể bằng Entity ở lớp con không?
- ORM sử dụng proxy subclass hay cơ chế khác?
- Việc lấy ID từ proxy có kích hoạt truy vấn không?
- Provider có API để lấy persistent class thực tế mà không phá vỡ equality không?

Nếu dùng Hibernate hoặc một ORM có proxy, hãy áp dụng cách xác định lớp persistent theo hướng dẫn của provider và phiên bản đang dùng. Một số API lấy lớp thật có thể khởi tạo proxy; cần cân nhắc tác động tải dữ liệu. Không nên sao chép một đoạn equals() trên mạng mà không kiểm thử với proxy và inheritance thực tế.

Với Entity không có inheritance, instanceof thường tương thích hơn với proxy subclass so với so sánh getClass() trực tiếp. Với hierarchy, hãy dùng một chính sách type check nhất quán, có xét đến proxy, để bảo đảm equals() vẫn đối xứng và bắc cầu.

Đặc biệt, không để lớp cha so sánh bằng instanceof trong khi lớp con lại yêu cầu hai đối tượng có cùng getClass(). Khi đó, đối tượng lớp cha có thể xem lớp con là bằng mình, nhưng chiều ngược lại trả về false, vi phạm tính đối xứng. Nếu các lớp con đại diện cho loại Entity khác nhau, equality cần so sánh persistent type thực tế theo cách tương thích với proxy của ORM.

### Không để equals/hashCode truy cập association lazy

Tránh đưa quan hệ như orders, payments, children hoặc collections vào equals/hashCode. Việc này có thể:

- Kích hoạt lazy loading ngoài dự kiến.
- Gây truy vấn database khi so sánh hoặc đưa Entity vào collection.
- Tạo vòng lặp nếu hai phía của quan hệ cùng tham chiếu nhau.
- Làm hash code thay đổi khi collection được tải hoặc thay đổi.
- Tăng chi phí và tạo lỗi khi Entity đã detached.

Equality của Entity nên dựa trên identity đã chọn, không dựa trên toàn bộ đồ thị đối tượng.

## 7. Equality của Entity trước và sau persistence

Một Entity thường trải qua các trạng thái:

| Trạng thái | Ý nghĩa | Lưu ý về equality |
| --- | --- | --- |
| Transient / New | Được tạo trong bộ nhớ, chưa được quản lý hoặc lưu | ID database-generated có thể null |
| Managed / Persistent | Được persistence context quản lý | ID có thể đã được gán |
| Detached | Từng được lưu nhưng hiện không còn được quản lý | Có thể được so sánh với instance khác cùng ID |
| Removed | Được đánh dấu xóa trong persistence context | Vẫn cần chính sách equality nhất quán trong thời gian object còn tồn tại |

Hai object Java khác nhau có thể đại diện cho cùng một bản ghi nếu một object được tải trong EntityManager thứ nhất và object kia được tải trong EntityManager thứ hai. Reference equality (==) sẽ là false, nhưng persistent identity equality có thể là true.

```java
Customer fromFirstContext = entityManagerA.find(Customer.class, 100L);
Customer fromSecondContext = entityManagerB.find(Customer.class, 100L);

boolean sameReference = fromFirstContext == fromSecondContext;
boolean sameEntity = fromFirstContext.equals(fromSecondContext);
```

Trong ví dụ, sameReference thường là false vì hai persistence context quản lý các instance riêng. Nếu equals() được thiết kế theo persistent identity, sameEntity có thể là true.

Cần phân biệt điều này với việc cùng một object được quản lý trong một persistence context. ORM thường bảo đảm identity map trong một context: cùng một entity type và primary key thường trả về cùng một instance. Nhưng quy tắc đó không giải quyết equality giữa các context khác nhau hoặc giữa managed và detached object.

## 8. Vì sao không nên dùng các thuộc tính có thể thay đổi

Một Entity có thể thay đổi tên, địa chỉ, trạng thái hoặc quan hệ. Nếu các thuộc tính đó tham gia hashCode(), hash code có thể thay đổi trong vòng đời.

Ví dụ không nên làm:

```java
@Override
public int hashCode() {
    return Objects.hash(name, email, status);
}
```

Nếu khách hàng đổi email hoặc trạng thái, hash code đổi. Nếu đối tượng đang ở trong HashSet, việc tìm kiếm hoặc xóa có thể thất bại.

Tương tự, không nên dùng toàn bộ field làm equality chỉ vì IDE hoặc Lombok có thể sinh tự động. Một Entity không phải Value Object. Equality cần phản ánh danh tính đã chọn, còn các thuộc tính mô tả có thể thay đổi không nên làm Entity trở thành một đối tượng khác.

### Cẩn thận với Lombok

Annotation **@Data** sinh equals(), hashCode(), toString(), getter và setter dựa trên các field theo quy tắc của Lombok. Với JPA Entity, cách sinh mặc định có thể đưa ID có thể null, association lazy và collection vào equality hoặc toString.

Nếu dùng Lombok, cần chỉ định rõ field nào tham gia equals/hashCode và hiểu tác động của ID được sinh muộn. Trong nhiều Entity, viết hai phương thức một cách tường minh dễ review hơn. Không dùng @Data một cách mặc định cho Entity có vòng đời và quan hệ ORM phức tạp.

## 9. Phân biệt Entity equality với unique constraint của database

equals/hashCode chỉ xác định cách các object Java được xem là bằng nhau trong bộ nhớ. Chúng không thay thế các ràng buộc toàn vẹn trong database.

Ví dụ, nếu mã hợp đồng phải duy nhất, database cần unique constraint hoặc unique index phù hợp. Hai request đồng thời có thể cùng kiểm tra rằng mã chưa tồn tại rồi cùng cố gắng insert. Chỉ kiểm tra trong equals() hoặc repository không thể bảo đảm tính duy nhất khi có concurrency.

Ngược lại, database primary key duy nhất không nhất thiết là business identity. Một khóa surrogate được sinh tự động có thể nhận diện dòng lưu trữ, trong khi nghiệp vụ dùng một mã hợp đồng hoặc mã khách hàng khác.

Cần xác định rõ:

- Khóa nào dùng cho identity của Entity trong mô hình?
- Khóa nào dùng để tra cứu theo nghiệp vụ?
- Khóa nào dùng làm primary key?
- Unique constraint nào cần được database bảo vệ?
- Phạm vi duy nhất là toàn hệ thống, theo tenant hay theo một Bounded Context?

Một giá trị chỉ duy nhất trong tenant cần có tenant identity trong phạm vi so sánh hoặc một cấu trúc định danh tương ứng. Nếu bỏ qua phạm vi, hai Entity thuộc hai tenant có thể bị xem là cùng một đối tượng.

## 10. Kiểm thử equals/hashCode theo vòng đời

Không nên chỉ kiểm tra hai Entity được tạo từ cùng ID có bằng nhau hay không. Hãy kiểm thử cả trạng thái transient, sau khi ID được gán, collection và proxy nếu dự án sử dụng ORM.

### Kiểm thử hai Entity transient khác nhau

```java
@Test
void twoNewCustomersAreNotEqual() {
    Customer first = new Customer();
    Customer second = new Customer();

    assertNotEquals(first, second);
    assertEquals(first, first);
}
```

### Kiểm thử cùng ID và hash code tương thích

```java
@Test
void customersWithSamePersistentIdAreEqual() {
    Customer first = customerWithId(100L);
    Customer second = customerWithId(100L);

    assertEquals(first, second);
    assertEquals(first.hashCode(), second.hashCode());
}
```

### Kiểm thử hash collection qua thời điểm persist

```java
@Test
void hashSetStillFindsCustomerAfterGeneratedIdIsAssigned() {
    Customer customer = new Customer();
    Set<Customer> customers = new HashSet<>();

    customers.add(customer);
    customer.assignGeneratedId(100L);

    assertTrue(customers.contains(customer));
}
```

Các phương thức tạo fixture hoặc gán ID trong ví dụ kiểm thử là chi tiết của test setup; ứng dụng thực tế không nên cung cấp setter công khai để người dùng tùy ý thay đổi persistence identity. Có thể dùng persistence test, package-private helper, reflection hoặc fixture phù hợp với kiến trúc để mô phỏng việc provider gán ID.

Ngoài ra, nên kiểm tra:

- Đối xứng: A.equals(B) và B.equals(A) có cùng kết quả.
- Bắc cầu: nếu A bằng B và B bằng C thì A bằng C.
- Khác loại Entity không bị xem là bằng nhau ngoài ý muốn.
- Detached object và managed object cùng ID có hành vi đúng.
- Proxy và Entity thật được so sánh đúng với ORM đang sử dụng.
- Hash code không thay đổi sau khi persist nếu chiến lược dựa trên ID sinh muộn.
- Không phát sinh truy vấn lazy ngoài dự kiến khi gọi equals/hashCode.

## 11. Quy trình lựa chọn và review

Khi thiết kế Entity, có thể dùng trình tự sau:

1. **Xác định identity nghiệp vụ.** Hỏi chuyên gia cách nhận diện một đối tượng và phạm vi duy nhất.
2. **Xác định thời điểm ID xuất hiện.** ID được cấp từ ứng dụng, từ nghiệp vụ hay do database sinh khi persist?
3. **Đánh giá khóa tự nhiên.** Khóa có duy nhất, bất biến và luôn sẵn có không?
4. **Xác định phạm vi Entity type.** Có kế thừa, nhiều tenant hoặc nhiều Bounded Context không?
5. **Chọn chiến lược equality.** Dùng business key bất biến, application-generated ID hoặc persistence ID với hash ổn định.
6. **Kiểm tra ORM behavior.** Xem xét proxy, lazy loading, inheritance và lifecycle callback.
7. **Kiểm thử collection.** Đặc biệt thử thêm Entity transient vào HashSet rồi persist và tìm lại.
8. **Bảo vệ dữ liệu ở database.** Thêm primary key, unique constraint và foreign key phù hợp; không dựa vào Java equality để thay thế.
9. **Review thay đổi về identity.** Nếu thay ID hoặc khóa nghiệp vụ, xem xét tác động đến collection, cache, association và API.

Checklist ngắn cho code review:

- [ ] equals() phản ánh identity của Entity trong đúng phạm vi.
- [ ] Hai Entity transient khác nhau không bị xem là bằng nhau chỉ vì ID null.
- [ ] equals() và hashCode() tuân thủ hợp đồng Java.
- [ ] hashCode() ổn định qua thời điểm persist nếu ID được gán muộn.
- [ ] Các field mutable không tham gia equality một cách tùy tiện.
- [ ] Association và collection lazy không nằm trong equals/hashCode.
- [ ] Proxy và inheritance đã có chính sách type check rõ ràng.
- [ ] Unique constraint của database bảo vệ các khóa cần duy nhất.
- [ ] Có kiểm thử cho transient, persistent, detached và HashSet/HashMap.

## 12. Những sai lầm thường gặp

- **So sánh hai ID null là bằng nhau:** mọi Entity mới có thể bị xem như cùng một đối tượng.
- **Dùng ID sinh muộn cho hashCode:** hash thay đổi sau persist và làm hỏng vị trí phần tử trong hash collection.
- **Dùng tất cả field làm equality:** thay đổi tên, trạng thái hoặc quan hệ khiến identity biến đổi.
- **Dùng association trong equals/hashCode:** có thể kích hoạt lazy loading, vòng lặp và truy vấn ngoài ý muốn.
- **Dùng getClass() mà không xét ORM proxy:** Entity thật và proxy có thể bị xem là khác lớp.
- **Dùng instanceof mà không xét inheritance:** hai lớp con khác nhau có thể bị xem là bằng nhau ngoài ý muốn.
- **Cho rằng primary key chính là business identity:** khóa lưu trữ và danh tính nghiệp vụ có thể khác nhau.
- **Cho rằng equals() bảo đảm unique trong database:** concurrency vẫn cần constraint ở nơi lưu trữ.
- **Để Lombok tự sinh equality cho Entity:** các field không phù hợp có thể bị đưa vào phép so sánh.

## Kết luận

Entity được nhận diện bằng danh tính ổn định trong mô hình, còn equals/hashCode là cách Java biểu diễn danh tính đó khi làm việc với object và collection. Khi ID được database sinh sau khi lưu, Entity transient chưa có ID và Entity persistent đã có ID phải được xử lý nhất quán. Không được xem mọi object có ID null là bằng nhau, cũng không nên để hash code thay đổi sau khi Entity đã nằm trong HashSet hoặc HashMap.

Hãy ưu tiên khóa nghiệp vụ bất biến nếu nó thực sự duy nhất và ổn định; nếu dùng ID sinh trước khi lưu, bảo đảm ID không đổi; nếu dùng database-generated ID, chọn cách equality và hash code phù hợp với vòng đời persistence, ORM proxy và inheritance. Cuối cùng, kiểm thử cả vòng đời Entity và dùng ràng buộc database để bảo vệ tính duy nhất ở nơi dữ liệu được lưu trữ.
