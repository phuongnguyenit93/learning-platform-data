# Kiểm tra entity được quản lý bằng `EntityManager.contains()`

## 1. Vì sao phải biết một entity có đang được quản lý?

Trong Jakarta Persistence (JPA), một object Java có thể đại diện cho một hàng trong cơ sở dữ liệu nhưng **không nhất thiết đang được JPA theo dõi**. Ví dụ, `Customer` vừa được tạo bằng `new`, một `Customer` tải bằng `EntityManager.find()`, và một `Customer` được lưu từ request trước đều có thể chứa cùng các thuộc tính nghiệp vụ, nhưng khả năng đồng bộ thay đổi của chúng không giống nhau.

Phương thức **`EntityManager.contains(Object entity)`** giúp trả lời câu hỏi cụ thể:

> **Instance entity này có đang ở trạng thái managed trong persistence context hiện tại hay không?**

Nó không trả lời “hàng này có tồn tại trong database không?”, “entity này đã được commit chưa?”, hay “object này có cùng ID với một managed entity khác không?”.

Ví dụ đơn giản:

```java
Customer customer = new Customer("An Nguyen");

System.out.println(em.contains(customer)); // false: object mới.

em.persist(customer);

System.out.println(em.contains(customer)); // true: đang managed.
```

Hai lần gọi được thực hiện với **cùng một `EntityManager em` đang mở**, trong giao dịch phù hợp. Điểm khác biệt nằm ở việc `persist()` đưa entity vào trạng thái managed. Không cần giả định rằng giao dịch đã commit hay rằng SQL `INSERT` đã được gửi trước khi `contains()` trả về `true`.

Bài học này tập trung vào các tình huống dùng `contains()` để nhận diện đúng **trạng thái quản lý của một instance**, đặc biệt sau `persist`, `find`, `merge`, `detach`, `clear` và `remove`; đồng thời phân biệt rõ trạng thái trong Java với dữ liệu thực tế ở database.

## 2. Persistence context là gì?

### 2.1. Không gian quản lý của JPA

**Persistence context** là tập hợp các entity instance đang được JPA quản lý và thông tin trạng thái cần thiết để phát hiện thay đổi, đồng bộ dữ liệu và duy trì identity trong một phạm vi nhất định.

`EntityManager` cung cấp các thao tác làm việc với persistence context:

```text
                   EntityManager em
                          |
                          v
                 Persistence Context
            +-----------------------------+
            |  Customer#10 -> instance A  |
            |  Customer#20 -> instance B  |
            |  Order#101   -> instance C  |
            |                             |
            |  snapshot / dirty checking  |
            +-----------------------------+
                          |
                flush / transaction
                          v
                     Database
```

Khi tải entity:

```java
Customer first = em.find(Customer.class, 10L);
Customer second = em.find(Customer.class, 10L);
```

Trong cùng persistence context, JPA duy trì một managed instance cho cùng một persistent identity; vì vậy hai lần tìm cùng entity thường trả về **chính cùng tham chiếu Java**:

```java
System.out.println(first == second);  // true, nếu đã tìm thấy.
System.out.println(em.contains(first)); // true.
```

Để hiểu `contains()`, hãy phân biệt:

- **Persistent identity:** loại entity và khóa chính dùng để nhận diện bản ghi trong phạm vi persistence unit.
- **Java object identity:** `a == b` kiểm tra hai biến có trỏ tới cùng một object hay không.
- **Managed state:** instance có đang được persistence context hiện tại quản lý hay không.
- **Database existence:** hàng có đang tồn tại trong database hay không, xét transaction và cơ chế nhìn thấy dữ liệu.

`contains()` chỉ kiểm tra thành phần thứ ba: **managed state của instance được truyền vào**.

### 2.2. EntityManager và phạm vi context

Hai `EntityManager` khác nhau thường có **persistence context riêng**. Cùng một hàng database có thể được biểu diễn bởi những instance khác nhau trong từng context:

```java
Customer inEm1 = em1.find(Customer.class, 10L);
Customer inEm2 = em2.find(Customer.class, 10L);

System.out.println(em1.contains(inEm1)); // true.
System.out.println(em2.contains(inEm2)); // true.

System.out.println(em1.contains(inEm2)); // false.
System.out.println(em2.contains(inEm1)); // false.
```

Ví dụ giả sử `em1` và `em2` là hai application-managed `EntityManager` còn mở, không dùng chung persistence context. Cùng giá trị ID không làm instance tự động chuyển sang context khác.

**Quy tắc:** một entity không “managed toàn ứng dụng”; nó được quản lý **bởi một persistence context cụ thể**.

### 2.3. Vòng đời cơ bản

```text
              new Customer(...)
                     |
                     v
                   NEW
              contains = false
                     |
                 em.persist
                     |
                     v
                  MANAGED <------- em.find / em.getReference
              contains = true
                   /     \
                  /       \ em.remove
 em.detach / em.clear       v
     / em.close           REMOVED
           |           contains = false
           v
        DETACHED
    contains = false
           |
    em.merge(detached)
           |
           +------> MANAGED COPY / INSTANCE
                    contains = true
                  (object gốc vẫn detached)
```

Sơ đồ tập trung vào trạng thái dùng với `contains`. Cần nhớ `remove`/`merge` còn có các quy tắc riêng theo trạng thái entity, cascade, transaction và lỗi dữ liệu.

## 3. Cách gọi `EntityManager.contains()`

### 3.1. Chữ ký API

Phương thức chuẩn JPA:

```java
boolean contains(Object entity);
```

Ví dụ:

```java
boolean managed = entityManager.contains(customer);
```

Kết quả:

- **`true`**: instance entity đang được quản lý trong persistence context hiện tại.
- **`false`**: instance entity không ở trạng thái managed trong context này; có thể new, detached, removed hoặc đang được một context khác quản lý.
- **`IllegalArgumentException`**: đối số không phải một entity hợp lệ đối với API, ví dụ một `Object` thông thường không được ánh xạ như entity.

Phải gọi trên `EntityManager` đang hoạt động. Nếu `EntityManager` đã đóng, các thao tác trên nó có thể ném `IllegalStateException`; không dùng `contains()` trên manager đã đóng để hỏi về trạng thái cũ.

### 3.2. Một ví dụ phân biệt entity với object thường

```java
Customer customer = new Customer("Mai");

boolean managed = em.contains(customer); // false vì chưa persist.

Object arbitrary = new Object();

// Không phải phép kiểm tra "false nếu là object bất kỳ":
// em.contains(arbitrary);  // Có thể ném IllegalArgumentException.
```

`contains()` **không phải phương thức Java tổng quát** để kiểm tra một object nằm trong collection. Nó yêu cầu đối tượng tham gia mô hình entity JPA.

Nếu ứng dụng nhận một giá trị có thể là `null` hoặc DTO, hãy kiểm tra/định kiểu trước khi gọi. Không dựa vào `contains()` để phát hiện một object “có annotation `@Entity` hay không”.

### 3.3. `contains()` không thực hiện truy vấn kiểm tra tồn tại

Ví dụ:

```java
Customer customer = new Customer("Khach hang moi");

boolean exists = em.contains(customer); // false.
```

`false` ở đây **không chứng minh database thiếu khách hàng có cùng email**. Tương tự, với một entity đã managed, `true` không xác nhận transaction hiện tại đã commit, hay rằng hàng vẫn tồn tại khi một transaction khác vừa xóa nó.

Việc kiểm tra managed state thường có thể được provider thực hiện từ thông tin của persistence context mà **không cần SELECT database**. Nó khác một truy vấn như `find`, `exists` hoặc `SELECT COUNT`. Tuy nhiên, các thao tác này cũng chịu ảnh hưởng của transaction isolation và cache; muốn bảo đảm điều kiện nghiệp vụ vẫn phải dùng ràng buộc và transaction phù hợp.

## 4. Tạo entity mới: `new` và `persist`

### 4.1. Trước `persist`

Entity Java mẫu:

```java
package com.example.shop.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "full_name", nullable = false, length = 120)
    private String fullName;

    protected Customer() {
    }

    public Customer(String fullName) {
        if (fullName == null || fullName.isBlank()) {
            throw new IllegalArgumentException("Tên không hợp lệ");
        }
        this.fullName = fullName;
    }

    public Long getId() {
        return id;
    }

    public String getFullName() {
        return fullName;
    }

    public void rename(String newName) {
        if (newName == null || newName.isBlank()) {
            throw new IllegalArgumentException("Tên không hợp lệ");
        }
        this.fullName = newName;
    }
}
```

Tạo instance mới:

```java
Customer customer = new Customer("Mai Nguyen");

System.out.println(customer.getId()); // null với Long generated ID.
System.out.println(em.contains(customer)); // false.
```

Vì `customer` chưa được đưa vào persistence context nên nó ở trạng thái **new/transient**. Điều này không phụ thuộc việc cùng tên có tồn tại trong database hay không.

### 4.2. Sau `persist`

```java
em.getTransaction().begin();

Customer customer = new Customer("Mai Nguyen");

System.out.println(em.contains(customer)); // false.

em.persist(customer);

System.out.println(em.contains(customer)); // true.

em.getTransaction().commit();
```

`persist` yêu cầu JPA quản lý instance mới, vì vậy `contains(customer)` trả về `true` sau khi thao tác hợp lệ. Với `GenerationType.IDENTITY`, provider thường phải phối hợp INSERT với database để lấy ID; thời điểm SQL thực thi có thể khác nhau theo provider và điều kiện transaction.

**Không đồng nhất `contains=true` với “đã INSERT và commit thành công”.** `persist` có thể tạo trạng thái managed trước khi database nhận dữ liệu, và transaction vẫn có thể rollback do lỗi constraint hoặc quy tắc khác.

### 4.3. Sau `flush`

```java
em.persist(customer);
em.flush();

System.out.println(em.contains(customer)); // true.
```

`flush` yêu cầu đồng bộ các thay đổi đang chờ với database trong transaction; nó **không chuyển entity sang detached**. Managed state tiếp tục tồn tại trong persistence context.

`flush` cũng **không phải commit**. Nếu transaction rollback, các tác động SQL chưa commit sẽ bị hủy, trong khi giá trị trong Java object không nhất thiết tự quay về như trước khi thao tác.

## 5. Tải entity: `find`, JPQL và `getReference`

### 5.1. `EntityManager.find()`

```java
Customer customer = em.find(Customer.class, 10L);

if (customer != null) {
    System.out.println(em.contains(customer)); // true.
}
```

`find` trả về entity được quản lý trong persistence context hiện tại, trừ các tình huống lỗi/điều kiện đặc biệt của môi trường. Nếu ID không tìm thấy, phương thức có thể trả về `null`; phải kiểm tra trước khi truy cập entity.

Hai lần `find` cùng ID trong một context:

```java
Customer one = em.find(Customer.class, 10L);
Customer two = em.find(Customer.class, 10L);

if (one != null) {
    System.out.println(one == two);     // true.
    System.out.println(em.contains(one)); // true.
}
```

JPA giữ nhất quán identity trong persistence context, nên không tạo hai managed instance khác nhau đại diện cùng một persistent identity trong cùng một context.

### 5.2. Kết quả truy vấn JPQL trả về entity

```java
List<Customer> customers = em.createQuery(
        "select c from Customer c where c.fullName like :prefix",
        Customer.class
    )
    .setParameter("prefix", "Mai%")
    .getResultList();

for (Customer customer : customers) {
    System.out.println(em.contains(customer)); // true trong context.
}
```

Các kết quả **entity** được JPA tải theo cách thông thường đều được quản lý bởi context hiện tại. Nhưng **DTO projection** khác entity:

```java
List<String> names = em.createQuery(
        "select c.fullName from Customer c",
        String.class
    )
    .getResultList();
```

`names` chứa `String`; không nên gọi `em.contains(name)`. Đây không phải entity được JPA quản lý, dù giá trị chuỗi được truy vấn từ một bảng entity.

Tương tự, kết quả `new CustomerDto(...)` trong JPQL constructor expression chỉ là DTO, không tự trở thành managed entity. Kiểm tra `contains` với DTO không trả lời bất cứ câu hỏi hữu ích nào về persistence context.

### 5.3. `getReference` và lazy proxy

```java
Customer reference = em.getReference(Customer.class, 10L);

System.out.println(em.contains(reference)); // managed reference.
```

`getReference` có thể trả về một proxy/lazy reference chưa tải đầy đủ dữ liệu từ database. Nó vẫn là một tham chiếu được quản lý theo mô hình JPA. Việc gọi `contains` **không phải cách kiểm tra hàng ID 10 chắc chắn tồn tại**.

Nếu hàng không tồn tại, provider có thể ném `EntityNotFoundException` khi thuộc tính của reference được truy cập; một số provider có thể phát hiện vấn đề sớm hơn. Vì thế:

- **`contains(reference) == true`**: reference nằm trong context.
- **Không suy ra**: database đang có hàng, tất cả field đã được tải, hoặc proxy đã initialized.
- Nếu use case bắt buộc xác nhận tồn tại ngay, dùng cách truy vấn và xử lý lỗi phù hợp.

Đừng gọi `getReference` chỉ nhằm tạo một object có `contains=true` rồi coi đó là phép kiểm chứng dữ liệu đầu vào.

## 6. `detach`: vẫn là entity nhưng không còn managed

### 6.1. Tách một entity

```java
Customer customer = em.find(Customer.class, 10L);

if (customer == null) {
    throw new IllegalArgumentException("Không tìm thấy Customer");
}

System.out.println(em.contains(customer)); // true.

em.detach(customer);

System.out.println(em.contains(customer)); // false.
```

Sau `detach`, `customer` vẫn là một Java object chứa ID và các giá trị đã được tải, nhưng JPA **không còn theo dõi thay đổi của instance đó** trong context hiện tại.

```java
customer.rename("Tên mới sau khi detach");

// Không thể mặc định mong thay đổi trên object detached được flush.
```

Nếu muốn cập nhật, phải dùng cách rõ ràng để đưa trạng thái thay đổi vào managed instance, ví dụ `merge` hoặc tải entity hiện có rồi cập nhật các field hợp lệ.

### 6.2. `detach` không xóa bản ghi

`em.detach(customer)` không có nghĩa “xóa Customer”. Nếu entity vẫn tồn tại trong database, một lần `find` khác có thể tải lại nó.

```java
em.detach(customer);
System.out.println(em.contains(customer)); // false.

Customer managedAgain = em.find(
    Customer.class,
    customer.getId()
);

System.out.println(em.contains(managedAgain)); // true.
System.out.println(em.contains(customer));     // false.
```

`managedAgain` là instance đang được context quản lý; `customer` cũ vẫn là detached. Chúng có thể có cùng ID nhưng không tự động là cùng Java object.

### 6.3. Cascade DETACH

Một association có thể khai báo `cascade = CascadeType.DETACH` hoặc `ALL`. Khi detach entity nguồn, JPA có thể lan truyền detach tới các entity liên quan theo cascade. Nhưng không nên giả định **mọi entity có liên quan qua khóa ngoại** cũng bị detach.

Tương tự, detach một entity không nhất thiết detach toàn bộ persistence context; những entity khác vẫn có thể managed. Muốn tách tất cả, dùng `clear` với nhận thức về tác động lên các thay đổi chưa flush.

## 7. `clear()`: mọi entity trong context bị tách

### 7.1. Khác biệt giữa `detach` và `clear`

- `em.detach(customer)`: chỉ tách một entity được chỉ định, với cascade DETACH nếu có.
- `em.clear()`: xóa toàn bộ các managed entity khỏi persistence context hiện tại theo semantics của API.

Ví dụ:

```java
Customer first = em.find(Customer.class, 10L);
Customer second = em.find(Customer.class, 20L);

System.out.println(em.contains(first));  // true.
System.out.println(em.contains(second)); // true.

em.clear();

System.out.println(em.contains(first));  // false.
System.out.println(em.contains(second)); // false.
```

Sau `clear`, hai object Java vẫn tồn tại trong bộ nhớ, nhưng không còn được JPA tự theo dõi.

### 7.2. `clear` có thể làm mất thay đổi chưa flush

```java
Customer customer = em.find(Customer.class, 10L);
customer.rename("Tên vừa sửa");

em.clear(); // Tách customer và bỏ các thay đổi chưa đồng bộ.
```

Nếu thao tác đổi tên chưa được flush, `clear` khiến JPA không còn snapshot cần thiết để ghi thay đổi đó. Đừng sử dụng `clear` như một “làm mới” vô hại.

Trong luồng batch xử lý hàng nghìn entity, có thể dùng:

```java
for (int i = 0; i < items.size(); i++) {
    Customer customer = items.get(i);

    // Xử lý customer trong context/transaction hiện có.

    if ((i + 1) % 100 == 0) {
        em.flush();
        em.clear();
    }
}
```

Đây chỉ là một đoạn minh họa quản lý bộ nhớ: các `items` đầu vào phải được xử lý theo trạng thái phù hợp, và sau mỗi `clear` những reference cũ không còn managed. Đừng tiếp tục sửa trực tiếp các object đã detached rồi mong JPA lưu chúng. `flush` trước `clear` giúp đồng bộ các thay đổi đang chờ, còn commit/rollback vẫn do transaction quyết định.

## 8. `merge`: kiểm tra đúng instance trả về

### 8.1. `merge` không biến đối số thành managed

Một tình huống rất thường gặp là nhận một entity detached từ request trước hoặc từ một `EntityManager` khác:

```java
Customer detached = ...; // Có ID, không còn được context hiện tại quản lý.

System.out.println(em.contains(detached)); // false.

Customer managed = em.merge(detached);

System.out.println(em.contains(detached)); // false.
System.out.println(em.contains(managed));  // true.
```

Điểm mấu chốt: **`merge()` trả về managed instance**. Đối số `detached` **không tự trở thành managed**.

Khi `merge` được gọi với một managed entity, provider có thể trả về chính instance đó; khi đối số là detached, JPA tìm/tạo managed instance tương ứng rồi sao chép state. Vì vậy, với luồng detached, hãy **sử dụng giá trị trả về**.

### 8.2. Dòng dữ liệu khi merge

```text
Context cũ:
  Customer#10 ── managed
         |
      em.close()
         |
         v
     detachedCustomer  (instance A)
         |
         | em2.merge(detachedCustomer)
         v
Context mới:
     managedCustomer   (instance B)
     cùng persistent ID nhưng là managed copy
     
em2.contains(instance A) = false
em2.contains(instance B) = true
```

Không nhầm `equals` theo ID với kết quả `contains`. Kể cả entity đã override `equals` khiến hai object bằng nhau về mặt Java, `contains` vẫn đánh giá **sự tham gia của chính instance đó** vào persistence context.

### 8.3. Ví dụ hoàn chỉnh với hai EntityManager

```java
EntityManager em1 = emf.createEntityManager();
Customer detached;

try {
    detached = em1.find(Customer.class, 10L);
    if (detached == null) {
        throw new IllegalArgumentException("Customer không tồn tại");
    }
} finally {
    em1.close(); // Entity đã tải không còn thuộc context em1.
}

detached.rename("Tên chỉnh sửa ở ngoài context");

EntityManager em2 = emf.createEntityManager();
try {
    em2.getTransaction().begin();

    System.out.println(em2.contains(detached)); // false.

    Customer managedCopy = em2.merge(detached);

    System.out.println(em2.contains(detached));    // false.
    System.out.println(em2.contains(managedCopy)); // true.

    em2.getTransaction().commit();
} catch (RuntimeException ex) {
    if (em2.getTransaction().isActive()) {
        em2.getTransaction().rollback();
    }
    throw ex;
} finally {
    em2.close();
}
```

Ví dụ giả định `emf` là một `EntityManagerFactory` đã khởi tạo và ứng dụng dùng `RESOURCE_LOCAL`. Trong hệ thống dùng container-managed transactions, cách nhận `EntityManager` và quản lý giao dịch khác.

**Lưu ý thực tế:** `merge` có thể sao chép nhiều field và association của detached graph theo mapping, chứ không chỉ một thuộc tính được sửa. Với dữ liệu từ API, thường an toàn và rõ ràng hơn khi tải managed entity rồi áp dụng thay đổi có mục tiêu, tránh ghi đè field ngoài ý định.

### 8.4. `merge` với object mới

`merge` cũng có thể nhận một entity mới/transient và tạo một managed instance tương ứng theo cơ chế merge. Nhưng:

```java
Customer original = new Customer("Một khách mới");

Customer result = em.merge(original);

System.out.println(em.contains(original)); // false.
System.out.println(em.contains(result));   // true.
```

Không dùng `merge` như cách tùy tiện thay thế `persist` trong mọi use case. `persist` biểu thị rõ ý định tạo entity mới, còn `merge` có semantics sao chép trạng thái và việc xác định new/detached theo JPA/provider.

## 9. `remove`: entity ở trạng thái removed không còn managed theo nghĩa `contains`

### 9.1. Xóa một managed entity

```java
Customer customer = em.find(Customer.class, 10L);

if (customer != null) {
    System.out.println(em.contains(customer)); // true.

    em.remove(customer);

    System.out.println(em.contains(customer)); // false: removed state.
}
```

Sau `remove`, object không biến mất khỏi bộ nhớ Java; nó mang trạng thái removed trong vòng đời persistence. SQL `DELETE` thường được thực hiện tại flush, và việc xóa được xác nhận khi transaction commit thành công.

**Không suy ra `contains=false` nghĩa là “entity đã bị xóa khỏi database”.** Trong trường hợp removed, thao tác xóa có thể đang chờ flush hoặc transaction còn khả năng rollback.

### 9.2. Không được `remove` một object detached như managed

```java
Customer detached = ...;

// Sai khi detached chưa được đưa vào context hiện tại:
// em.remove(detached);
```

`remove` yêu cầu đúng trạng thái entity theo JPA. Với detached entity, provider có thể ném `IllegalArgumentException`. Một cách xử lý rõ ràng là tìm managed instance bằng ID:

```java
Customer managed = em.find(Customer.class, detached.getId());

if (managed != null) {
    em.remove(managed);
}
```

Việc chọn xóa bằng ID phải kèm kiểm tra quyền, ràng buộc nghiệp vụ, version và ngữ cảnh giao dịch. Đừng dùng một đối số detached từ client làm căn cứ duy nhất cho quyền xóa.

### 9.3. `contains` và `remove` dùng cho hai mục đích khác nhau

`contains(entity)` là **truy vấn trạng thái quản lý**. `remove(entity)` là **lệnh thay đổi vòng đời**. Không nên viết logic “nếu `contains=false` thì `remove` sẽ tạo bản ghi xóa đúng” — vì false có thể là transient, detached hoặc removed.

Ví dụ:

```java
if (!em.contains(customer)) {
    // Chưa thể kết luận phải persist, merge hay find để xóa.
    // Cần biết intent của use case và nguồn gốc customer.
}
```

## 10. Một bảng trạng thái để nhận biết kết quả

Giả sử `em` là `EntityManager` đang mở và các thao tác đều hợp lệ trong cùng persistence context.

| Sự kiện | Trạng thái của instance được hỏi | `em.contains(instance)` | Điều không được suy ra |
|---|---|---|---|
| `new Customer(...)` | New/transient | `false` | Không biết đã có hàng cùng dữ liệu nghiệp vụ chưa |
| `em.persist(newCustomer)` | Managed | `true` | Chưa chắc SQL INSERT đã commit |
| `em.find(Customer.class, id)` tìm thấy | Managed | `true` | Không bảo đảm dữ liệu không đổi bởi transaction khác |
| JPQL trả về `Customer` entity | Managed | `true` | Không có nghĩa DTO/scalar cũng là entity |
| `em.getReference(...)` hợp lệ | Managed reference/proxy | `true` | Không bảo đảm đã tải field hoặc hàng tồn tại |
| `em.flush()` với entity managed | Vẫn managed | `true` | Flush chưa phải commit |
| `em.refresh(managed)` | Vẫn managed | `true` | Không phải thao tác attach một detached object |
| `em.detach(managed)` | Detached | `false` | Bản ghi DB vẫn có thể tồn tại |
| `em.clear()` | Tất cả instance cũ detached | `false` | Không tự xóa dữ liệu DB |
| `em.merge(detached)` — kiểm tra đối số | Vẫn detached | `false` | Đối số không trở thành managed |
| `em.merge(detached)` — kiểm tra return value | Managed | `true` | Không bảo đảm transaction đã commit |
| `em.remove(managed)` | Removed | `false` | DELETE có thể chưa flush/commit |
| Instance managed bởi một `EntityManager` khác | Không managed trong `em` này | `false` | Hai instance có thể trỏ cùng một DB row |
| `em.close()` | Context bị đóng | Không nên gọi `contains` tiếp | Các object cũ không còn được manager này quản lý |

Đây là bảng về **instance và context**, không phải bảng kết quả kiểm tra tồn tại trong database.

## 11. `contains` không phải `equals`, `==`, hoặc kiểm tra khóa chính

### 11.1. Cùng ID nhưng khác Java instance

```java
Customer managed = em.find(Customer.class, 10L);
Customer another = new Customer("Bản dựng từ request");

// Giả sử có cách đưa ID 10 vào another bằng mapping hoặc
// object detached được tải từ một context khác.
```

Trong thực tế, nếu `another` cũng có ID 10 nhưng không được chính `em` quản lý, `em.contains(another)` vẫn là `false`. Điều này không phụ thuộc hai object có cùng khóa hay không.

Một ví dụ không phải tự gán ID:

```java
Customer managed = em.find(Customer.class, 10L);

EntityManager otherEm = emf.createEntityManager();
try {
    Customer fromOtherContext =
        otherEm.find(Customer.class, 10L);

    System.out.println(managed == fromOtherContext); // false.
    System.out.println(em.contains(managed));        // true.
    System.out.println(em.contains(fromOtherContext)); // false.
} finally {
    otherEm.close();
}
```

### 11.2. Override `equals/hashCode` không quyết định managed state

Một entity có thể override `equals` theo non-null ID. Dù `managed.equals(detached)` cho kết quả true theo policy Java, chỉ instance thuộc persistence context mới có `contains=true`.

Ngược lại, một entity sử dụng reference equality mặc định vẫn có thể managed bình thường. `EntityManager.contains()` không đòi hỏi entity override `equals`/`hashCode` để hoạt động.

**Đừng dùng `contains` như phép kiểm tra trùng ID trong collection hoặc phép kiểm tra entity value equality.** Nó được thiết kế cho một câu hỏi hẹp hơn.

### 11.3. Không kiểm tra `contains` bằng ID thuần

```java
Long customerId = 10L;

// Sai: Long không phải entity được quản lý.
// em.contains(customerId);
```

Muốn tìm entity, dùng `find(Customer.class, customerId)`. Muốn kiểm tra tồn tại trong database theo yêu cầu nghiệp vụ, sử dụng truy vấn/constraint/transaction phù hợp. `contains` chỉ nhận **entity instance**.

## 12. Trong Spring và môi trường container-managed: chú ý ranh giới transaction

### 12.1. `@PersistenceContext` không có nghĩa context sống mãi

Ứng dụng Spring hoặc Jakarta EE thường dùng injection:

```java
@PersistenceContext
private EntityManager entityManager;
```

Đối tượng được inject có thể là proxy hoặc facade của context được quản lý theo transaction. Khi một service xử lý giao dịch, entity được tải hoặc persist trong phạm vi đó sẽ ở trạng thái managed.

Ví dụ Spring:

```java
@Service
public class CustomerService {

    @PersistenceContext
    private EntityManager em;

    @Transactional
    public void renameCustomer(Long id, String newName) {
        Customer customer = em.find(Customer.class, id);

        if (customer == null) {
            throw new IllegalArgumentException("Không tìm thấy khách");
        }

        if (!em.contains(customer)) {
            throw new IllegalStateException("Customer không managed");
        }

        customer.rename(newName);
        // Dirty checking có thể cập nhật khi transaction flush.
    }
}
```

Đây là minh họa dùng Spring `@Service` và `@Transactional` với cấu hình JPA phù hợp. Kiểm tra `contains` trong luồng này thường **không cần thiết về chức năng**: `find` đã cung cấp managed entity. Nó hữu ích để học hoặc chẩn đoán khi code có nhiều nguồn object khác nhau.

### 12.2. Ra khỏi transaction, kết quả có thể khác

Với **transaction-scoped persistence context** do container quản lý, những entity đã tải trong transaction có thể trở thành detached khi context kết thúc. Một method ở request tiếp theo có thể dùng một context khác; không được mặc định rằng object giữ trong biến hoặc cache ứng dụng vẫn managed.

Tuy nhiên, cũng không được khẳng định **“commit luôn khiến entity detached”**. Ví dụ application-managed `EntityManager` dùng `RESOURCE_LOCAL` có thể tiếp tục giữ một persistence context qua nhiều transaction nếu `EntityManager` vẫn mở. `EXTENDED` persistence context cũng có vòng đời dài hơn transaction thông thường.

**Managed state phụ thuộc vào context đang kiểm tra, không chỉ vào thời điểm commit**.

### 12.3. Không chia sẻ EntityManager giữa các thread tùy tiện

`EntityManager` và persistence context có trạng thái theo dõi, không được thiết kế để ứng dụng tự chia sẻ một instance application-managed giữa nhiều thread cùng lúc. Một entity được quản lý trong transaction của request A không tự được quản lý trong request B.

Việc truyền entity qua queue, cache, session HTTP hoặc serialization thường làm object có vai trò **detached data** ở nơi nhận. Dùng DTO để trao đổi qua ranh giới request/service là mô hình dễ kiểm soát hơn khi không cần toàn bộ semantics của managed entity.

## 13. Những điều `contains` **không** xác nhận

### 13.1. Không chứng minh hàng vẫn còn trong database

Giả sử entity được tải và một transaction khác xóa hàng tương ứng. Trước khi context hiện tại refresh/flush hoặc truy vấn phát hiện xung đột, `em.contains(entity)` vẫn có thể true vì instance vẫn được quản lý trong context của nó.

Nếu business rule cần xác nhận hàng tồn tại và không bị thay đổi đồng thời, phải dựa vào transaction isolation, version/optimistic locking, truy vấn hoặc constraint, không chỉ `contains`.

### 13.2. Không chứng minh SQL đã được gửi

```java
em.persist(customer);
boolean tracked = em.contains(customer); // true.
```

`tracked` không nói có bao nhiêu SQL `INSERT` đã chạy. Với `IDENTITY`, provider có thể cần INSERT sớm để lấy khóa; với `SEQUENCE`, ID có thể được cấp trước INSERT. Chỉ quan sát SQL thực tế và ranh giới transaction mới kết luận được.

### 13.3. Không chứng minh transaction thành công

`em.contains(customer) == true` trước commit không bảo đảm commit sẽ thành công. Một `UNIQUE` constraint, `FOREIGN KEY`, lỗi kết nối hoặc optimistic locking có thể khiến transaction rollback.

### 13.4. Không đoán entity có dirty hay không

```java
Customer customer = em.find(Customer.class, 10L);
customer.rename("Tên khác");

System.out.println(em.contains(customer)); // true.
```

Kết quả true không cho biết provider đã đánh dấu dirty hoặc có SQL UPDATE cần phát. Một managed entity có thể chưa đổi, có thể đổi, hoặc dirty state có thể cần xử lý theo provider/type mapping.

Nếu cần kiểm tra thay đổi ở mức Hibernate, có các API provider-specific; đừng nhầm `EntityManager.contains` là API chuẩn để kiểm tra dirty flag.

### 13.5. Không xác nhận lazy association đã initialized

Một proxy/collection có thể chưa tải mà entity chủ vẫn managed. `contains` không phải là phép kiểm tra trạng thái khởi tạo lazy proxy.

Theo Jakarta Persistence, `PersistenceUnitUtil.isLoaded(...)` có thể hữu ích để kiểm tra trạng thái tải. Provider như Hibernate còn có công cụ riêng. Dù vậy, kiểm tra lazy loading và kiểm tra managed state là hai câu hỏi khác nhau.

### 13.6. Không đồng nghĩa entity có thể được sửa tùy ý

Managed entity có thể nằm trong transaction read-only, là một entity bị hạn chế theo nghiệp vụ, hoặc việc thay đổi một association có thể vi phạm ràng buộc. `contains=true` chỉ nói context theo dõi instance, không cấp quyền sửa dữ liệu.

Quyền truy cập và chính sách cập nhật phải được kiểm tra riêng theo người dùng, tenant, transaction và domain rules.

### 13.7. Không bảo vệ concurrency

Hai context cùng quản lý hai instance khác nhau của cùng một hàng đều có thể trả `true` khi kiểm tra với context của chúng. Điều đó không ngăn việc hai transaction ghi đè nhau.

Dùng `@Version`, locking, constraint hoặc quy tắc concurrency thích hợp khi nghiệp vụ cần phát hiện xung đột.

## 14. Khi nào nên gọi `contains`?

`contains` hữu ích khi **nguồn gốc object không chắc chắn**, hoặc khi cần debug quản lý trạng thái:

| Tình huống | Dùng `contains` có ích? | Giải thích |
|---|---|---|
| Sau `find` ngay trong cùng method | Thường không cần | `find` đã trả managed entity nếu tìm thấy |
| Trước khi cập nhật một instance đến từ cache/request cũ | Có thể có | Cho biết instance đó có thuộc context hiện tại không |
| Sau `merge`, so sánh input và return value | Rất có ích khi học/debug | Cho thấy copy managed khác detached input |
| Sau `detach`/`clear` | Có ích khi chẩn đoán | Xác nhận reference cũ đã ra khỏi context |
| Khi kiểm tra `getReference` có tải dữ liệu chưa | Không đúng mục đích | Cần API kiểm tra lazy initialization |
| Khi kiểm tra một ID có tồn tại trong database | Không đúng mục đích | Cần `find`/query hoặc constraint |
| Khi kiểm tra entity đã commit chưa | Không đúng mục đích | Phụ thuộc transaction/flush/commit |
| Khi quyết định user có quyền sửa record không | Không đúng mục đích | Cần authorization |
| Khi phát hiện bug “đã set nhưng DB không đổi” | Có ích trong chẩn đoán | Có thể object đang detached hoặc ở context khác |
| Khi kiểm tra entity thuộc request/session khác | Có ích nếu đúng context được kiểm tra | Không được dùng trên manager đã đóng |

**Không nên thêm `em.contains(...)` vào mọi method CRUD.** Nhiều khi luồng code đã xác định rõ entity managed vì vừa `find` trong transaction, kiểm tra sẽ chỉ tăng độ ồn. Giá trị lớn nhất của `contains` là giúp **giải thích và chẩn đoán** khi trạng thái entity trở nên khó theo dõi.

## 15. Tình huống debug: sửa object nhưng database không đổi

### 15.1. Lỗi phổ biến: sửa detached instance

```java
Customer detached = loadCustomerInPreviousRequest();

// Request hiện tại:
detached.rename("Tên mới");

// Không có managed entity được cập nhật trong context hiện tại.
```

Bản thân setter chỉ sửa bộ nhớ Java. Nếu `detached` không managed, dirty checking của context hiện tại không theo dõi nó.

Có thể kiểm tra:

```java
System.out.println(em.contains(detached)); // false.
```

Giải pháp tập trung theo ID:

```java
@Transactional
public void changeName(Long customerId, String newName) {
    Customer managed = em.find(Customer.class, customerId);
    if (managed == null) {
        throw new IllegalArgumentException("Không tìm thấy customer");
    }
    managed.rename(newName);
}
```

Cách này tránh việc merge tràn lan những field của một object detached không còn phản ánh dữ liệu mới nhất.

### 15.2. Lỗi phổ biến: bỏ qua return value của `merge`

```java
Customer detached = ...;

em.merge(detached);

detached.rename("Tên sửa sau merge");
// Đối số vẫn detached; thay đổi tiếp trên nó không tự được theo dõi.
```

Cách đúng khi có lý do dùng merge:

```java
Customer managed = em.merge(detached);

managed.rename("Tên sửa sau merge");
System.out.println(em.contains(managed));  // true.
System.out.println(em.contains(detached)); // false.
```

Vẫn cần một transaction phù hợp để dữ liệu được đồng bộ và commit.

### 15.3. Lỗi phổ biến: `clear` quá sớm

```java
Customer managed = em.find(Customer.class, 10L);
managed.rename("Tên A");
em.clear(); // Bỏ thay đổi chưa flush.

managed.rename("Tên B");
// Lúc này object đã detached.
```

`em.contains(managed)` sau `clear` là false. Nếu việc clear là chủ đích để giới hạn memory trong batch, phải flush trước khi clear khi muốn giữ các thay đổi đã chuẩn bị, và sau clear nên tải lại entity hoặc xử lý phần còn lại theo context mới.

### 15.4. Lỗi phổ biến: kiểm tra ở sai EntityManager

```java
Customer fromEm1 = em1.find(Customer.class, 10L);

System.out.println(em1.contains(fromEm1)); // true.
System.out.println(em2.contains(fromEm1)); // false.
```

Đừng diễn giải kết quả false của `em2` thành “entity đã bị delete”. Nó chỉ không được `em2` quản lý.

### 15.5. Lỗi phổ biến: thấy true nhưng vẫn ghi không thành công

```java
Customer managed = em.find(Customer.class, 10L);
System.out.println(em.contains(managed)); // true.

managed.rename("Tên không được phép theo quy tắc nào đó");
```

Nếu transaction rollback do constraint, lỗi đồng thời hoặc business validation, database không nhận thay đổi cuối cùng. `contains=true` không bảo đảm commit.

Quy trình debug nên tách **managed state**, **transaction**, **SQL/flush**, **constraint** và **dữ liệu đọc lại sau commit** thay vì đổ mọi vấn đề vào `contains`.

## 16. Trường hợp entity graph và cascade

### 16.1. `cascade=PERSIST` tạo managed child

Ví dụ đơn hàng có nhiều dòng:

```java
@Entity
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @OneToMany(
        mappedBy = "order",
        cascade = CascadeType.PERSIST
    )
    private List<OrderLine> lines = new ArrayList<>();

    public void addLine(OrderLine line) {
        lines.add(line);
        line.setOrder(this);
    }
}
```

```java
@Entity
public class OrderLine {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "order_id")
    private PurchaseOrder order;

    public void setOrder(PurchaseOrder order) {
        this.order = order;
    }
}
```

Ở ví dụ tập trung vào lifecycle, các class entity cần constructor không tham số và import tương ứng. Trước khi lưu:

```java
PurchaseOrder order = new PurchaseOrder();
OrderLine line = new OrderLine();
order.addLine(line);

System.out.println(em.contains(order)); // false.
System.out.println(em.contains(line));  // false.
```

Sau:

```java
em.persist(order);

System.out.println(em.contains(order)); // true.
System.out.println(em.contains(line));  // true khi PERSIST cascade được áp dụng.
```

Đây là một trường hợp **cascade thao tác vòng đời**: persist cha làm con được quản lý. Nhưng việc lưu khóa ngoại `order_id` vẫn phải căn cứ vào owning side `OrderLine.order`; chỉ thêm line vào collection phía inverse mà không gọi `line.setOrder(order)` có thể làm FK không được thiết lập đúng.

### 16.2. Không có cascade thì kết quả khác

Nếu bỏ `cascade=PERSIST`, thêm `new OrderLine` vào collection không đồng nghĩa line tự managed. Với quan hệ có FK bắt buộc, JPA có thể báo lỗi khi flush do tham chiếu transient chưa được lưu.

Lúc đó có thể chủ động:

```java
em.persist(order);
em.persist(line);
```

cùng với việc thiết lập quan hệ theo đúng owning side, hoặc chọn cascade phù hợp quy tắc ownership của domain.

### 16.3. `contains` không cho biết quan hệ đã ghi đúng

Hai kết quả `em.contains(order) == true` và `em.contains(line) == true` không chứng minh `line.order_id` đã được ghi đúng hoặc association hai chiều đồng bộ. Managed state là thông tin về **instance**, trong khi relationship được ghi theo owning side, flush và schema.

## 17. Batch update/delete và trạng thái stale

### 17.1. JPQL bulk UPDATE không đồng bộ tự động managed entity

Giả sử đã tải:

```java
Customer customer = em.find(Customer.class, 10L);
System.out.println(em.contains(customer)); // true.
```

Sau đó chạy bulk JPQL:

```java
em.createQuery(
        "update Customer c set c.fullName = :name where c.id = :id"
    )
    .setParameter("name", "Tên cập nhật trực tiếp")
    .setParameter("id", 10L)
    .executeUpdate();
```

Bulk update làm việc trực tiếp qua query và **không tự cập nhật trạng thái của tất cả managed instances** trong persistence context. Vì vậy, `em.contains(customer)` vẫn có thể true nhưng `customer.getFullName()` có thể giữ giá trị cũ.

Đây là ví dụ quan trọng cho thấy **managed không đồng nghĩa luôn mới nhất so với database**.

Khi phối hợp bulk update/delete với managed entities, phải có chính sách `flush` trước khi chạy bulk nếu có pending changes liên quan, và `clear`/`refresh`/tách transaction sau đó phù hợp. `clear` làm các reference cũ detached; `refresh` yêu cầu managed entity và có thể gặp lỗi nếu hàng bị xóa.

### 17.2. JPQL bulk DELETE và `contains`

Sau bulk delete:

```java
em.createQuery(
        "delete from Customer c where c.id = :id"
    )
    .setParameter("id", 10L)
    .executeUpdate();
```

một `Customer#10` đã managed trong context có thể **vẫn được context quản lý** (contains true) nhưng bản ghi database đã bị xóa bởi bulk query. Vì thao tác bulk không đi qua lifecycle `remove` cho từng instance, trạng thái context cần được xử lý rõ ràng.

Không dùng `contains=false/true` để quyết định bulk DELETE thành công. Kết quả `executeUpdate()` là số hàng bị ảnh hưởng theo semantics query; database constraints và transaction vẫn cần được xử lý.

## 18. Kiểm tra với ví dụ runnable sử dụng `RESOURCE_LOCAL`

Để quan sát các trạng thái theo một luồng rõ ràng, có thể viết mã trong ứng dụng Java SE đã cấu hình persistence unit `demoPU` với một datasource JDBC và entity `Customer`.

### 18.1. Entity mẫu

Entity `Customer` ở phần 4 dùng:

- `@Entity`, `@Table(name = "customers")`.
- `@Id` + `@GeneratedValue(strategy = IDENTITY)`.
- `Long id` và `String fullName`.
- Constructor JPA không tham số và method `rename`.

Schema tương đương PostgreSQL:

```sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    full_name VARCHAR(120) NOT NULL
);
```

Đối với H2 hoặc một RDBMS khác, dùng cú pháp identity và driver tương ứng.

### 18.2. Chuỗi thao tác minh họa

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.Persistence;

public class ContainsWalkthrough {

    public static void main(String[] args) {
        EntityManagerFactory emf =
            Persistence.createEntityManagerFactory("demoPU");

        EntityManager em = emf.createEntityManager();

        try {
            em.getTransaction().begin();

            Customer original = new Customer("Mai Nguyen");

            System.out.println(em.contains(original)); // 1. false

            em.persist(original);
            System.out.println(em.contains(original)); // 2. true

            em.flush();
            Long id = original.getId();
            System.out.println(em.contains(original)); // 3. true

            em.detach(original);
            System.out.println(em.contains(original)); // 4. false

            Customer reloaded = em.find(Customer.class, id);
            System.out.println(em.contains(reloaded)); // 5. true
            System.out.println(em.contains(original)); // 6. false

            original.rename("Mai Detached");

            Customer merged = em.merge(original);
            System.out.println(em.contains(original)); // 7. false
            System.out.println(em.contains(merged));   // 8. true

            em.clear();
            System.out.println(em.contains(reloaded)); // 9. false
            System.out.println(em.contains(merged));   // 10. false

            Customer forRemoval = em.find(Customer.class, id);
            System.out.println(em.contains(forRemoval)); // 11. true

            em.remove(forRemoval);
            System.out.println(em.contains(forRemoval)); // 12. false

            em.getTransaction().commit();
        } catch (RuntimeException ex) {
            if (em.getTransaction().isActive()) {
                em.getTransaction().rollback();
            }
            throw ex;
        } finally {
            em.close();
            emf.close();
        }
    }
}
```

Mã minh họa trên giả định database bắt đầu ở trạng thái không có lỗi constraint hoặc ID conflict, transaction commit bình thường và provider tuân theo semantics JPA. `em.flush()` trước `detach` giúp entity mới đã được đồng bộ trong transaction trước khi bị tách.

### 18.3. Diễn giải kết quả

| Lần in | Instance được kiểm tra | Vì sao? | Kết quả kỳ vọng |
|---|---|---|---|
| 1 | `original` mới | Chưa persist | `false` |
| 2 | `original` sau persist | Được context theo dõi | `true` |
| 3 | `original` sau flush | Flush không detach | `true` |
| 4 | `original` sau detach | Instance bị tách | `false` |
| 5 | `reloaded` sau find | Instance managed được tải lại | `true` |
| 6 | `original` sau find một instance khác | Original vẫn detached | `false` |
| 7 | `original` sau merge | Input vẫn detached | `false` |
| 8 | `merged` do merge trả về | Managed instance | `true` |
| 9 | `reloaded` sau clear | Context bị clear | `false` |
| 10 | `merged` sau clear | Context bị clear | `false` |
| 11 | `forRemoval` sau find | Managed instance mới trong context | `true` |
| 12 | `forRemoval` sau remove | Removed state | `false` |

Có thể gặp một chi tiết quan trọng ở bước 8: vì `reloaded` đã có cùng ID và đang managed trong context trước `merge`, `merged` có thể chính là `reloaded`. Điều không đổi là **`original` vẫn detached**, và **giá trị trả về `merged` được managed**.

`original.rename("Mai Detached")` trước `merge` là một thay đổi trên detached instance; nó chỉ được sao chép sang managed entity khi gọi merge. Sau `clear`, những managed reference trước đó đều bị tách.

Mẫu này cố ý thực hiện `remove` ở cuối. Nếu muốn tiếp tục thử `find`/`refresh` trên cùng ID sau khi remove, nên chuẩn bị dữ liệu thử nghiệm mới hoặc transaction khác; không lẫn trạng thái removed với các thao tác tra cứu thông thường.

## 19. Các hiểu nhầm thường gặp

| Nhận định | Cách hiểu đúng |
|---|---|
| “`contains(entity)` kiểm tra entity có trong database không.” | Nó kiểm tra instance có đang managed trong context hiện tại không. |
| “Có ID thì chắc chắn managed.” | Object có ID có thể detached hoặc đến từ context khác. |
| “`contains=false` nghĩa là object mới.” | Có thể new, detached, removed hoặc managed ở context khác. |
| “`contains=true` nghĩa là đã commit.” | Entity có thể managed trước flush/commit. |
| “Sau `persist` phải gọi `flush` thì `contains` mới true.” | `persist` hợp lệ đưa entity vào managed state; flush không phải điều kiện cần để hỏi trạng thái. |
| “`detach` xóa hàng khỏi database.” | Detach chỉ tách khỏi persistence context. |
| “`clear` chỉ xóa cache mà không ảnh hưởng việc ghi.” | Clear tách các entity và có thể bỏ thay đổi chưa flush. |
| “`merge(detached)` khiến object đầu vào managed.” | Managed object là **giá trị trả về** của merge; đối số vẫn detached. |
| “Hai instance có cùng ID thì `contains` giống nhau.” | Kết quả phụ thuộc đúng instance và đúng context. |
| “`getReference` rồi `contains=true` chứng minh hàng tồn tại.” | Proxy có thể managed mà chưa cần kiểm tra hàng thực. |
| “Managed entity thì giá trị luôn mới nhất trong database.” | Bulk query hoặc transaction khác có thể khiến object stale. |
| “`contains=true` nghĩa là entity đang dirty.” | Managed state và dirty state là hai khái niệm khác. |
| “Entity đã bị `remove` thì object Java biến mất.” | Object vẫn ở bộ nhớ và chuyển sang removed state. |
| “Commit luôn làm entity detached.” | Phụ thuộc loại và vòng đời persistence context. |
| “`contains` có thể kiểm tra DTO hoặc ID Long.” | DTO/ID scalar không phải entity; gọi chứa đối số không phải entity là sai mục đích. |

## 20. Bài thực hành

### Bài 1 — New, persist và flush

Tạo `Customer` với `@GeneratedValue(IDENTITY)`, mở transaction, rồi in kết quả `em.contains(customer)` trước persist, sau persist và sau flush. Quan sát SQL INSERT và ID thực tế.

Câu hỏi: vì sao một entity có thể `contains=true` dù transaction chưa commit?

### Bài 2 — Detach và tải lại

Sau khi lưu một Customer, gọi `em.detach(customer)`, tiếp tục sửa `fullName` trên object cũ. Tải lại cùng ID bằng `find` rồi so sánh `contains` của hai instance.

Câu hỏi: vì sao cùng ID nhưng chỉ một instance được managed? Vì sao setter trên detached object không tự tạo UPDATE?

### Bài 3 — Merge phải dùng return value

Tạo hai persistence context: tải Customer ở context thứ nhất rồi đóng nó; cập nhật tên trên detached object; gọi `merge` trong context thứ hai.

Kiểm tra:

```java
Customer managed = em2.merge(detached);

System.out.println(em2.contains(detached));
System.out.println(em2.contains(managed));
```

Câu hỏi: vì sao dùng biến `detached` để sửa tiếp sau merge là một rủi ro?

### Bài 4 — Clear và thay đổi chưa flush

Tải entity managed, gọi `rename("A")`, sau đó `em.clear()` mà chưa flush. Quan sát kết quả `contains`, rồi đọc lại database.

Lặp lại bằng cách gọi `em.flush()` trước `em.clear()` trong cùng transaction. So sánh thay đổi nào được đồng bộ trước khi context bị tách.

### Bài 5 — Remove và transaction

Tải entity managed, gọi `em.remove(entity)`, in `contains` trước và sau remove. Quan sát SQL DELETE tại flush/commit và kiểm tra dữ liệu sau khi commit thành công.

Câu hỏi: vì sao `contains=false` ngay sau remove không có nghĩa DELETE đã commit?

### Bài 6 — Hai EntityManager

Tạo `em1` và `em2` riêng, mỗi context tải cùng một ID. So sánh kết quả:

```java
em1.contains(a);
em1.contains(b);
em2.contains(a);
em2.contains(b);
```

Câu hỏi: tại sao hai object cùng persistent identity có thể managed trong hai persistence context riêng nhưng không managed chéo nhau?

### Bài 7 — Bulk update tạo stale managed entity

Trong cùng transaction, tải một Customer bằng `find`, sau đó chạy bulk JPQL UPDATE đổi `fullName` của Customer đó. In `contains(customer)` và đọc `customer.getFullName()`.

Thử `refresh(customer)` hoặc làm sạch context rồi truy vấn lại để nhận dữ liệu phù hợp. Câu hỏi: vì sao managed state không bảo đảm field đồng bộ ngay với bulk SQL?

### Bài 8 — Proxy không chứng minh database existence

Lấy reference bằng `getReference` cho một ID, gọi `contains(reference)`, rồi thử truy cập thuộc tính không phải ID và xử lý tình huống bản ghi thiếu.

Câu hỏi: làm thế nào phân biệt việc reference được quản lý, việc proxy đã được khởi tạo và việc hàng thật tồn tại?

### Bài 9 — Cascade persist

Tạo `PurchaseOrder` mới và hai `OrderLine` mới với `cascade=PERSIST`. Kiểm tra `contains` của cả ba trước và sau `em.persist(order)`, rồi thử bỏ cascade để quan sát khác biệt.

Câu hỏi: vì sao cascade có thể làm các child trở thành managed nhưng không tự bảo đảm owning side của quan hệ đã được thiết lập đúng?

## 21. Ghi nhớ cốt lõi

**`EntityManager.contains(entity)` trả lời duy nhất câu hỏi “instance này có đang được persistence context hiện tại quản lý không?”** Nó là phép kiểm tra managed state, không phải truy vấn kiểm tra tồn tại dữ liệu, tình trạng commit, dirty checking, lazy loading hay quyền cập nhật.

Trong luồng làm việc thông thường, `persist` và `find` đưa entity vào managed state; `detach`/`clear` tách entity khỏi context; `merge` trả về một managed instance nhưng **không gắn lại chính object detached được truyền vào**; `remove` chuyển managed entity sang removed state. Sau `close` không tiếp tục gọi `contains` trên `EntityManager` cũ.

Khi gặp vấn đề “sửa object nhưng database không đổi”, hãy xác định **đúng instance, đúng `EntityManager`, đúng persistence context, đúng transaction và đúng thao tác flush/commit**. `contains` là công cụ chẩn đoán hữu ích cho phần *đúng instance và context*, nhưng không thay thế các bước còn lại.
