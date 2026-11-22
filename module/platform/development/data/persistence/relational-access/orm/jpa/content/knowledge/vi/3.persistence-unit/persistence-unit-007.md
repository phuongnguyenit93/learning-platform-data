# Phân biệt ngữ cảnh theo giao dịch và ngữ cảnh mở rộng trong JPA

Trong Jakarta Persistence (JPA), **persistence context** (ngữ cảnh bền vững) là tập hợp những **entity instance đang được quản lý** bởi JPA provider. Context giúp bảo đảm cùng một entity identity được biểu diễn bằng cùng một managed instance trong phạm vi context, theo dõi thay đổi thuộc tính (dirty checking) và đồng bộ dữ liệu sang cơ sở dữ liệu quan hệ khi cần.

Khi dùng **container-managed EntityManager** trong Jakarta EE, có hai kiểu persistence context chính:

- **Transaction-scoped persistence context**: gắn với một giao dịch JTA; thường kết thúc khi giao dịch kết thúc.
- **Extended persistence context**: có vòng đời kéo dài qua nhiều lời gọi và nhiều giao dịch; thường gắn với một **stateful session bean**.

Chúng có thể cùng dùng **một persistence unit**, cùng nguồn dữ liệu và cùng lớp `@Entity`. Điều khác biệt là **thời gian entity tiếp tục ở trạng thái managed**, chứ không phải hai cách ánh xạ bảng khác nhau.

## 1. Persistence unit, EntityManager và persistence context liên hệ thế nào?

| Thành phần | Nó xác định điều gì? | Khái niệm cần phân biệt |
| --- | --- | --- |
| **Persistence unit (PU)** | Tập entity metadata, nguồn dữ liệu và các thiết lập JPA/provider có tên, ví dụ `shopPU` | Cấu hình persistence, không phải tập entity instance hiện thời |
| **EntityManagerFactory** | Tạo `EntityManager` theo cấu hình PU | Factory, không phải transaction hay connection JDBC đơn lẻ |
| **EntityManager** | API `find`, `persist`, `merge`, `remove`, `flush`… | Cách ứng dụng thao tác với context |
| **Persistence context** | Những instance đang managed, trạng thái cần ghi, identity map | Trạng thái runtime; có thể ngắn hoặc dài hơn một transaction |
| **DataSource** | Nơi cấp JDBC connection tới database | Không quyết định vòng đời managed entity |

~~~text
                       Persistence unit "shopPU"
                  entity mapping + DataSource + JTA
                                  |
                          EntityManager
                                  |
                       Persistence context
                       /                 \
                      /                   \
            TRANSACTION-SCOPED            EXTENDED
               theo T1, T2...          theo vòng đời
                                      stateful bean
~~~

Không đồng nhất **persistence context**, **transaction** và **JDBC connection**. Extended context có thể sống khi không có transaction; provider có thể lấy/trả connection theo nhu cầu thay vì giữ một connection mở từ đầu đến cuối hội thoại.

## 2. Transaction-scoped persistence context

### 2.1. Định nghĩa và vòng đời

Transaction-scoped context là mặc định của `@PersistenceContext` với container-managed EntityManager. Khi một phương thức làm việc trong giao dịch JTA T1, context được gắn với T1. Các instance `find()` trả về trong context đó là **managed**; thay đổi trên chúng có thể được đồng bộ với DB khi flush hoặc commit.

Khi T1 kết thúc, transaction-scoped context cũng kết thúc, và các entity instance do context đó quản lý trở thành **detached**. Một giao dịch T2 sau đó sẽ có context gắn với T2; object Java giữ từ T1 không tự trở thành managed trong T2.

~~~text
    Bắt đầu T1           Đọc/sửa                 Commit T1
         |                 |                         |
         +-----------------+-------------------------+
                  Persistence context PC1
                  Customer#10 = managed
                                                   -> detached

                                               Bắt đầu T2    Commit T2
                                                   |            |
                                                   +------------+
                                                        PC2
~~~

**Phạm vi theo giao dịch không có nghĩa là theo phương thức.** Nếu nhiều lời gọi EJB tham gia cùng một JTA transaction được truyền qua các component phù hợp, chúng có thể chia sẻ context của transaction đó. Ngược lại, hai lần gọi một phương thức trong hai transaction khác nhau sẽ không mặc nhiên dùng chung context.

Khi không có transaction hiện hành, container-managed transaction-scoped EntityManager không duy trì một managed context xuyên các lời gọi như extended context. Chẳng hạn, entity đọc ở một thao tác không có transaction không nên được giả định là còn managed để ghi dữ liệu trong thao tác sau.

### 2.2. Ví dụ trên một stateless service

Giả sử đã có entity `Customer` với các trường `id` và `name` cùng phương thức `setName`. Trong Jakarta EE:

~~~java
package com.example.shop;

import jakarta.ejb.Stateless;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import jakarta.persistence.PersistenceContextType;

@Stateless
public class CustomerService {
    @PersistenceContext(
        unitName = "shopPU",
        type = PersistenceContextType.TRANSACTION
    )
    private EntityManager em;

    public void rename(Long id, String newName) {
        Customer customer = em.find(Customer.class, id);
        if (customer == null) {
            throw new IllegalArgumentException("Customer not found");
        }

        customer.setName(newName);
        // Entity đang managed; JPA theo dõi thay đổi trong transaction.
    }
}
~~~

EJB container-managed transaction mặc định thường sử dụng `REQUIRED`. Với một giao dịch đang hoạt động, lệnh `rename()` sẽ:

1. Lấy `Customer` từ DB hoặc context hiện hành.
2. Đưa instance vào trạng thái managed trong context của transaction.
3. Ghi nhận thay đổi `name`; không nhất thiết chạy SQL ngay khi gọi setter.
4. Flush các cập nhật cần thiết khi thích hợp và commit nếu lời gọi thành công.
5. Kết thúc context theo giao dịch khi transaction hoàn tất.

`type = PersistenceContextType.TRANSACTION` là giá trị mặc định; có thể viết đơn giản `@PersistenceContext(unitName = "shopPU")`.

### 2.3. Trường hợp sử dụng

Phạm vi này phù hợp với CRUD, REST endpoint, cập nhật một đơn hàng, tính tiền, thay đổi trạng thái nghiệp vụ, xử lý event và những thao tác trong **một transaction ngắn, rõ ràng**. Vì context không giữ managed object qua những lượt tương tác dài, ứng dụng dễ quản lý tài nguyên và giảm nguy cơ dữ liệu cũ trong memory.

## 3. Extended persistence context

### 3.1. Định nghĩa

Extended context tồn tại **xuyên nhiều transaction**. Trong mô hình Jakarta EE container-managed, nó thường được tạo cùng **stateful session bean** và tiếp tục tồn tại tới khi bean bị hủy hoặc vòng đời của nó kết thúc.

~~~text
Tạo stateful bean                                       Hủy bean
       |                                                    |
       +----------------------------------------------------+
                        Extended context PCx
       |                |                 |                 |
      T1             không TX             T2                T3
  find(Order)      sửa Order         flush/commit         find(Item)
       |                |                 |
       +----------------+-----------------+
       Order vẫn có thể là managed instance trong PCx
~~~

Context dài hơn giao dịch **không có nghĩa** giao dịch được giữ mở trong suốt phiên người dùng. Ví dụ một form nhiều bước có thể giữ đối tượng đang managed trong context, trong khi mỗi bước không mở transaction ghi. Đến lúc xác nhận, context mới tham gia transaction để flush.

Extended context cũng không tự bảo đảm rằng các thay đổi chỉ được lưu ở nút “Save”. Nếu nó tham gia một transaction trước đó, dirty checking/flush tại transaction đó **đã có thể ghi dữ liệu**. Thiết kế ranh giới transaction vẫn là yếu tố quyết định.

### 3.2. Cách khai báo

~~~java
import jakarta.ejb.Stateful;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import jakarta.persistence.PersistenceContextType;

@Stateful
public class OrderEditor {
    @PersistenceContext(
        unitName = "shopPU",
        type = PersistenceContextType.EXTENDED
    )
    private EntityManager em;
}
~~~

Khác với `@Stateless`, stateful bean có vòng đời gắn với một phiên hội thoại/đơn vị làm việc cụ thể. Container-managed extended persistence context được khởi tạo trong phạm vi stateful session bean; không thể chuyển nguyên ví dụ sang stateless bean rồi kỳ vọng vẫn giữ managed entity qua mỗi request.

### 3.3. Ví dụ: sửa đơn hàng nhiều bước

Giả sử entity `PurchaseOrder` đã có `getId()` và `setShippingAddress(String)`. Người dùng mở đơn hàng, sửa địa chỉ, sau đó chọn **Lưu** hoặc **Hủy**. Đây là ví dụ EJB minh họa extended context:

~~~java
package com.example.shop;

import jakarta.ejb.Remove;
import jakarta.ejb.Stateful;
import jakarta.ejb.TransactionAttribute;
import jakarta.ejb.TransactionAttributeType;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import jakarta.persistence.PersistenceContextType;

@Stateful
public class OrderEditor {
    @PersistenceContext(
        unitName = "shopPU",
        type = PersistenceContextType.EXTENDED
    )
    private EntityManager em;

    private PurchaseOrder current;

    @TransactionAttribute(TransactionAttributeType.NOT_SUPPORTED)
    public void open(Long orderId) {
        current = em.find(PurchaseOrder.class, orderId);
        if (current == null) {
            throw new IllegalArgumentException("Order not found");
        }
    }

    @TransactionAttribute(TransactionAttributeType.NOT_SUPPORTED)
    public void changeAddress(String address) {
        if (current == null) {
            throw new IllegalStateException("Open an order first");
        }
        current.setShippingAddress(address);
        // Đối tượng còn managed; chưa mở transaction ghi.
    }

    @Remove
    @TransactionAttribute(TransactionAttributeType.REQUIRED)
    public void saveAndClose() {
        if (current == null) {
            throw new IllegalStateException("Open an order first");
        }
        em.flush();
        // Container commit nếu lời gọi và transaction thành công.
    }

    @Remove
    @TransactionAttribute(TransactionAttributeType.NOT_SUPPORTED)
    public void cancelAndClose() {
        em.clear(); // Hủy các thay đổi chưa flush và detach entity.
    }
}
~~~

Đường đi qua các bước:

1. Container tạo một stateful `OrderEditor` và extended context PCx của nó.
2. `open()` không mở transaction; `find()` tải đối tượng vào PCx. Nếu chưa có đơn hàng, phương thức báo lỗi.
3. `changeAddress()` sửa instance vẫn managed trong PCx, dù không có giao dịch ghi.
4. `saveAndClose()` mở/tham gia transaction `REQUIRED`; PCx tham gia transaction theo chế độ đồng bộ mặc định, rồi `flush()` thực hiện SQL cần thiết. Container commit khi xử lý thành công và kết thúc bean được đánh dấu `@Remove`.
5. Nếu chọn `cancelAndClose()`, context được clear và bean bị hủy; những thay đổi **chưa được flush/commit** sẽ không được lưu.

Đoạn code có ý nghĩa minh họa vòng đời, không bắt buộc mọi giao diện chỉnh sửa phải dùng EJB stateful. Nếu một bước trước đó đã mở transaction và commit thay đổi, gọi “Cancel” ở bước sau **không đảo ngược** transaction đã commit.

## 4. Bảng so sánh trực tiếp

| Tiêu chí | Transaction-scoped | Extended |
| --- | --- | --- |
| Gắn với | Một transaction JTA | Vòng đời stateful component/conversation |
| Khai báo | `@PersistenceContext(type = TRANSACTION)` | `@PersistenceContext(type = EXTENDED)` |
| Mặc định | Có | Không |
| Component thường gặp | Stateless service, component container-managed | Stateful session bean |
| Sau khi transaction kết thúc | Context giao dịch kết thúc, entity trở thành detached | Entity có thể tiếp tục managed trong cùng extended context |
| Transaction mới | Dùng context theo transaction mới; `find` hoặc `merge` khi cần | Context đang có có thể tham gia transaction mới |
| Dirty checking | Trong context của transaction | Có thể theo dõi entity qua nhiều bước |
| Thời điểm ghi DB | Khi context flush trong transaction | Khi extended context tham gia transaction và flush |
| Bộ nhớ | Thường giữ entity trong thời gian ngắn | Có thể giữ nhiều entity/collection lâu hơn |
| Phù hợp | Nghiệp vụ độc lập, transaction ngắn | Hội thoại nhiều bước cần giữ managed state |
| Cần chú ý | Detached entity, lazy loading ngoài context | Dữ liệu cũ, xung đột đồng thời, chi phí bộ nhớ, commit sớm |

**Ví dụ với cùng đơn hàng số 10:**

~~~text
                  TRANSACTION                     EXTENDED

T1                PC1                              PCx
                  find(Order#10)                   find(Order#10)
                  Order managed                    Order managed

T1 kết thúc       PC1 kết thúc                     PCx vẫn còn
                  Order detached                   Order vẫn managed

T2                PC2                              PCx
                  find/merge khi cần               tiếp tục sửa Order
                  flush/commit                     flush/commit

Sau T2            PC2 kết thúc                     PCx tiếp tục
                                                   tới khi bean kết thúc
~~~

Một persistence unit có thể phục vụ nhiều context. Hai stateful bean có thể sử dụng cùng `shopPU` mà vẫn có các extended context riêng. Việc chia sẻ/propagate context giữa stateful component, nếu có, phải tuân theo quy tắc container và chuỗi lời gọi; không suy ra chỉ từ tên PU.

## 5. Managed, detached và `merge()`

### 5.1. Các trạng thái entity

- **New/transient**: object mới tạo, chưa được persistence context quản lý.
- **Managed**: object nằm trong context; thay đổi được provider theo dõi.
- **Detached**: object không còn thuộc context, ví dụ context theo transaction kết thúc hoặc gọi `clear()`.
- **Removed**: entity đang managed và được đánh dấu xóa để xử lý khi flush.

Ví dụ cùng một `@Entity` nhưng ở hai transaction khác nhau:

~~~java
// Giả định từng đoạn chạy trong transaction riêng.

// T1
Customer customerInT1 = em.find(Customer.class, 10L);
customerInT1.setName("Mai");
// T1 commit -> context theo T1 kết thúc.

// T2
customerInT1.setName("Mai Anh"); // Sửa detached object.
Customer customerInT2 = em.merge(customerInT1);
// Sử dụng customerInT2: instance managed trong context của T2.
~~~

Đoạn mã biểu diễn **ý tưởng trạng thái**, không phải toàn bộ chương trình tạo transaction. Với `merge`, provider **sao chép trạng thái** từ detached object sang managed instance và trả về instance đó. Đối số đầu vào không tự biến thành managed.

Trong nhiều nghiệp vụ, nếu client chỉ gửi ID và vài thuộc tính cần cập nhật thì phương án rõ ràng hơn là `find(id)` trong transaction mới, xác thực quyền và áp dụng từng thuộc tính được phép sửa. Tránh merge mù quáng cả một detached graph cũ.

### 5.2. Extended context giữ managed state lâu hơn

Trong extended context, instance tải ở T1 có thể tiếp tục managed sau T1, được chỉnh sửa trước T2 và đồng bộ trong T2. Vì thế không cần `merge` lại **chính instance vẫn đang managed**. Tuy nhiên, vì object có thể tồn tại lâu, thông tin trong memory có thể cũ so với dữ liệu do transaction khác cập nhật.

## 6. Flush, commit và transaction boundary

Để phân biệt đúng, cần hiểu ba hành động:

1. **Thay đổi managed entity**: sửa trường trong Java; provider ghi nhận thay đổi, chưa chắc đã tạo SQL ngay.
2. **Flush**: đồng bộ thay đổi đang chờ thành SQL trong transaction phù hợp. Flush không có nghĩa transaction đã commit.
3. **Commit**: kết thúc transaction thành công để thay đổi trở nên bền vững theo cơ chế DB.

| Tình huống | Điều có thể xảy ra |
| --- | --- |
| Transaction-scoped, T1 sửa entity rồi commit | Flush trong T1, commit, PC1 kết thúc |
| Extended, bước 1 không có transaction, bước 2 mới mở T2 | Thay đổi vẫn được theo dõi, rồi flush/commit trong T2 nếu context tham gia |
| Extended, bước 1 có T1 và commit | Thay đổi có thể đã được ghi và commit ở T1 dù UI chưa bấm “Save cuối cùng” |
| Bất kỳ context nào, flush xong nhưng transaction rollback | SQL đã flush không được commit |

Vì thế, câu “extended context chỉ ghi khi người dùng nhấn Save” **không đúng trong mọi thiết kế**. Muốn triển khai Save/Cancel thực sự, cần kiểm soát rõ transaction nào được phép ghi và transaction nào không.

### 6.1. Hai kịch bản đối chiếu

**Kịch bản A — mỗi bước có transaction:**

~~~text
T1: đọc Order -> sửa tên -> commit      (có thể UPDATE)
T2: sửa địa chỉ        -> commit      (có thể UPDATE)
T3: người dùng bấm Save -> commit
~~~

Trong kịch bản này, nhấn Cancel sau T2 không thể tự hủy các commit trước. Extended context không mang lại tính nguyên tử qua các transaction đã commit.

**Kịch bản B — các bước sửa chỉ tác động vào context, transaction ghi ở bước cuối:**

~~~text
Mở hội thoại -> đọc Order -> sửa field A -> sửa field B
                  (không có transaction ghi)
                                     |
                                 Save -> T2
                                     |
                            join transaction
                                     |
                                flush/commit
~~~

Đây mới là cách phối hợp context và transaction phù hợp với ví dụ lưu một lần. Đổi lại, context dài hạn có chi phí bộ nhớ và rủi ro dữ liệu cũ.

### 6.2. Synchronized và unsynchronized context

Jakarta Persistence còn cho phép khai báo:

~~~java
@PersistenceContext(
    unitName = "shopPU",
    type = PersistenceContextType.EXTENDED,
    synchronization = jakarta.persistence.SynchronizationType.UNSYNCHRONIZED
)
private EntityManager em;
~~~

- `SYNCHRONIZED` (mặc định): container-managed context được đồng bộ với transaction mà nó tham gia.
- `UNSYNCHRONIZED`: context chưa tự động tham gia JTA transaction; khi muốn đồng bộ trong transaction thích hợp phải gọi `em.joinTransaction()`.

**Phạm vi sống** (TRANSACTION/EXTENDED) và **chế độ tham gia transaction** (SYNCHRONIZED/UNSYNCHRONIZED) là hai chiều cấu hình khác nhau. `UNSYNCHRONIZED` không thay thế việc thiết kế transaction và quy tắc Save/Cancel hợp lý.

## 7. Khác với application-managed EntityManager

Khai báo `@PersistenceContext(type = ...)` ở trên mô tả **container-managed context**. Trong Java SE hoặc khi ứng dụng tự tạo EntityManager bằng factory:

~~~java
EntityManager em = emf.createEntityManager();
try {
    // Ứng dụng điều khiển transaction và vòng đời EntityManager.
    // Context gắn với EntityManager này đến khi đóng nó.
} finally {
    em.close();
}
~~~

Đây là **application-managed EntityManager**. Ứng dụng tự quyết định khi nào tạo/đóng nó. Một application-managed EM có thể tồn tại qua nhiều transaction nếu được giữ mở, nhưng điều đó không đồng nghĩa với việc nó được container inject bằng `@PersistenceContext(type = EXTENDED)`.

`EntityManager` **không thread-safe**. Không chia sẻ một EM đang managed qua nhiều request/thread song song. Thường có thể dùng chung `EntityManagerFactory` rồi tạo EntityManager theo phạm vi công việc thích hợp.

Trong Spring Data JPA, proxy EntityManager/transaction manager thường quản lý context theo transaction; không nên suy luận rằng inject một field EntityManager sẽ giữ nguyên một persistence context cho mọi request.

## 8. Tác động lên tính nhất quán và tài nguyên

### 8.1. Entity giữ lâu có thể bị cũ

Người dùng A mở đơn hàng bằng extended context. Sau đó B sửa cùng đơn hàng và commit. Instance trong context của A có thể vẫn mang giá trị cũ; JPA không tự refresh mọi managed entity khi database thay đổi.

Đối với cập nhật cạnh tranh, dùng **optimistic locking** với `@Version` khi phù hợp:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Version;

@Entity
public class PurchaseOrder {
    @Id
    private Long id;

    @Version
    private long version;

    // Các trường nghiệp vụ, getters/setters...
}
~~~

Provider có thể dựa trên version để phát hiện cập nhật xung đột khi ghi. Ứng dụng cần bắt lỗi optimistic locking, yêu cầu người dùng tải lại hoặc thực hiện quy trình giải quyết xung đột.

### 8.2. Extended context giữ nhiều managed object

Một hội thoại tải thêm hàng trăm entity và collection có thể làm context lớn lên, khiến bộ nhớ và việc theo dõi thay đổi tốn kém. Nên giới hạn dữ liệu giữ lâu, tải đúng những gì cần thiết và chấm dứt stateful conversation khi hoàn thành/hủy.

`em.detach(entity)` tách một entity khỏi context. `em.clear()` tách toàn bộ managed entities; sau đó những thay đổi chưa đồng bộ trên các detached object không còn được provider tự theo dõi.

### 8.3. Rollback không phải “undo” Java object

Rollback hủy tác động của transaction ở database, nhưng **không tự đảo ngược các lệnh gán thuộc tính đã chạy trong Java**. Sau khi transaction thất bại, không nên coi trạng thái trong memory vẫn chắc chắn khớp database; cần xử lý vòng đời context và tải lại dữ liệu theo yêu cầu nghiệp vụ/provider.

### 8.4. Không giữ database transaction mở suốt một form

Một transaction kéo dài khi người dùng nhập liệu có thể giữ lock và tài nguyên DB quá lâu. Extended persistence context cho phép lưu trạng thái nghiệp vụ qua nhiều bước **mà không cần duy trì một transaction hoặc connection liên tục**. Transaction ghi nên được mở ở điểm commit nghiệp vụ thích hợp.

## 9. Chọn loại context theo bài toán

**Ưu tiên transaction-scoped** khi nghiệp vụ có transaction ngắn và rõ: tạo khách hàng, đặt hàng, thanh toán, cập nhật profile, xử lý REST API. Đây là lựa chọn phổ biến vì ít giữ state lâu, dễ kiểm soát lỗi và dễ mở rộng theo request độc lập.

**Dùng extended** khi thật sự có một **hội thoại nghiệp vụ nhiều bước** ở tầng stateful component, trong đó cần giữ managed entity identity qua nhiều transaction và có kế hoạch rõ cho lưu/hủy, timeout, xung đột concurrent update.

Trong ứng dụng web stateless, một cách tiếp cận khác thường đơn giản là giữ **DTO draft** thay cho extended context:

~~~text
Request 1: GET Order -> ánh xạ thành EditOrderDto -> hiển thị form
Người dùng sửa DTO trong giao diện qua nhiều bước
Request 2: POST DTO -> bắt đầu transaction ngắn
                 -> find Order trong context hiện hành
                 -> kiểm tra quyền/validate/áp dụng trường cần đổi
                 -> commit
~~~

Cách này không đòi hỏi duy trì managed entity lâu trong phiên người dùng, đồng thời giúp backend quyết định chính xác những dữ liệu nào được cập nhật.

## 10. Các hiểu lầm thường gặp

| Hiểu lầm | Cách hiểu đúng |
| --- | --- |
| “Một persistence unit có đúng một persistence context.” | Một PU có thể phục vụ rất nhiều context ở những transaction/conversation khác nhau. |
| “Transaction-scoped tức là một context cho một Java method.” | Gắn theo transaction; nhiều method có thể cùng tham gia transaction. |
| “Extended là giao dịch rất dài.” | Extended là context dài; transaction không cần kéo dài. |
| “Extended tự động trì hoãn commit cho tới nút Save.” | Nếu context tham gia transaction trước, thay đổi có thể đã commit trước đó. |
| “Có object Java trong biến thì chắc chắn nó managed.” | Trạng thái managed phụ thuộc context hiện hành và vòng đời context. |
| “`merge()` biến đối số detached thành managed.” | `merge()` trả về managed instance khác (hoặc managed instance phù hợp), đối số vẫn detached. |
| “Transaction kết thúc thì field EntityManager được inject biến mất.” | Container có thể giữ proxy/reference EntityManager; context gắn với transaction mới là thứ kết thúc. |
| “Giữ extended context giúp dữ liệu luôn mới.” | Entity có thể stale; phải cân nhắc refresh, versioning và cập nhật cạnh tranh. |

## 11. Bài tập tình huống có lời giải

**Tình huống 1.** Stateless `CustomerService` sử dụng `TRANSACTION`. T1 tải `Customer#5`, sửa tên và commit. T2 cần chỉnh số điện thoại. T2 có được tự động theo dõi instance Java giữ từ T1 không?

**Trả lời:** Không. Context của T1 đã kết thúc, object từ T1 đã detached. Trong T2, thường nên truy vấn lại `Customer#5` bằng `find()` rồi cập nhật, hoặc sử dụng `merge()` khi có lý do phù hợp.

**Tình huống 2.** Stateful `OrderEditor` dùng `EXTENDED`, T1 tải đơn hàng và kết thúc. Sau đó người dùng sửa địa chỉ ngoài transaction, rồi T2 lưu. Entity có còn managed ở T2 không?

**Trả lời:** Có thể vẫn managed trong extended context, nếu bean/context chưa kết thúc và object chưa bị detach/clear. Context tham gia T2 để đồng bộ thay đổi.

**Tình huống 3.** Cũng với extended context, bước đầu đã sửa thông tin và commit trong T1. Bước sau người dùng chọn Cancel. Cancel có tự khôi phục DB về trước T1 không?

**Trả lời:** Không. Commit T1 đã hoàn tất; phải thiết kế lại ranh giới transaction/draft hoặc dùng thao tác bù trừ nếu nghiệp vụ yêu cầu.

**Tình huống 4.** Hai stateful bean cùng sử dụng persistence unit `shopPU`. Chúng có luôn chia sẻ một extended context không?

**Trả lời:** Không thể suy ra điều đó từ tên PU. Mỗi bean có thể giữ context riêng; propagation giữa stateful beans chỉ có khi thỏa điều kiện trong quy tắc container và chuỗi lời gọi tương ứng.

## 12. Ghi nhớ theo một câu hỏi

Khi muốn biết đối tượng `Order` còn được JPA theo dõi sau khi giao dịch kết thúc hay không, hãy hỏi: **persistence context của nó sống đến khi nào?**

- Với **transaction-scoped**, context gắn với transaction vừa kết thúc; entity của context đó không còn managed.
- Với **extended**, context có thể tiếp tục tồn tại sau transaction; entity có thể vẫn managed tới khi stateful conversation kết thúc.

Trong cả hai cách, **persistence unit** vẫn định nghĩa entity mapping và nguồn dữ liệu, còn **transaction** quyết định ranh giới đồng bộ/commit dữ liệu. Chọn phạm vi context theo vòng đời nghiệp vụ, đồng thời thiết kế transaction rõ ràng để tránh lưu sớm, giữ state quá lâu hoặc cập nhật bằng dữ liệu đã cũ.
