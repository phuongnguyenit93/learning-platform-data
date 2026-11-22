# Mapping quan hệ, cascade, orphan removal và lazy loading trong Spring Data JPA

**Spring Data JPA** giúp truy xuất entity qua repository, nhưng hành vi **quan hệ, khóa ngoại, cascade, orphan removal và lazy loading** chủ yếu đến từ **Jakarta Persistence** và JPA provider như **Hibernate**. Chỉ cần đặt sai **mappedBy**, chọn **CascadeType.ALL** trên một quan hệ dùng chung hoặc đọc collection **LAZY** ngoài persistence context, ứng dụng có thể lưu sai khóa ngoại, xóa nhầm bản ghi, phát sinh N+1 queries hoặc lỗi LazyInitializationException.

Bài này đi từ mô hình bảng đến đối tượng Java, phân biệt ownership và vòng đời, giải thích **cascade khác orphanRemoval**, hiểu lúc SQL được flush, kiểm chứng LAZY trong và ngoài persistence context, và chọn **@EntityGraph/JPQL JOIN FETCH** cho truy vấn cần dữ liệu con. Ví dụ hoàn chỉnh dùng **Java 17, Spring Boot 3.4.5, Spring Data JPA, Hibernate 6.6.x do Boot quản lý, H2, JUnit Jupiter và @DataJpaTest**. Các lệnh test được nêu cùng kết quả **dự kiến**, không ngụ ý đã chạy Gradle thực tế trong bài.

## 1. Quan hệ object không tự động giống quan hệ trong database

Giả sử ứng dụng có một **PurchaseOrder** chứa nhiều **OrderLine**. Quan hệ vật lý trong RDBMS có một khóa ngoại:

~~~text
purchase_orders                      order_lines
+-----------------+               +----------------------+
| id (PK)         | 1         N   | id (PK)              |
| order_code      |<--------------| order_id (FK)        |
+-----------------+               | sku                  |
                                  | quantity             |
                                  | unit_price           |
                                  +----------------------+
~~~

Ở Java, bạn muốn đi cả hai hướng:

- Từ PurchaseOrder: **getLines()** để đọc danh sách OrderLine.
- Từ OrderLine: **getOrder()** để biết nó thuộc PurchaseOrder nào.

Hai thuộc tính Java không có nghĩa database cần hai khóa ngoại. Trong ánh xạ hai chiều kiểu **@OneToMany** / **@ManyToOne**, thường chỉ **OrderLine.order** là **owning side** vì cột **order_id** nằm ở bảng order_lines. Phía PurchaseOrder.lines dùng **mappedBy = "order"** để nói đây là **inverse side**, cùng đại diện cho một mối quan hệ vật lý.

**Quan hệ có direction/ownership và vòng đời entity là hai chuyện độc lập.** Việc parent nắm collection không làm parent tự trở thành phía quản lý khóa ngoại. Việc owner là child cũng không ngăn parent cấu hình cascade để propagate persist/remove đến các child.

## 2. Bốn annotation quan hệ thường gặp

| Mapping | Cardinality | Cột/bảng liên kết thông thường | Fetch mặc định theo JPA |
| --- | --- | --- | --- |
| **@OneToOne** | Mỗi phía tối đa một | Foreign key duy nhất hoặc shared primary key | **EAGER** |
| **@OneToMany** | Một cha có nhiều con | FK tại bảng con, hoặc join table tùy kiểu mapping | **LAZY** |
| **@ManyToOne** | Nhiều con tham chiếu một cha | FK tại bảng con | **EAGER** |
| **@ManyToMany** | Nhiều–nhiều | Join table với hai FK | **LAZY** |

Điểm dễ gây bất ngờ: **@ManyToOne và @OneToOne mặc định EAGER** theo Jakarta Persistence. Nếu bạn không cần luôn lấy parent ngay khi truy xuất child, thường nên khai báo rõ **fetch = FetchType.LAZY** tại **@ManyToOne**. LAZY của to-one có thể dựa vào Hibernate proxy hoặc bytecode enhancement; một số trường hợp @OneToOne inverse/optional có điều kiện riêng. **LAZY là yêu cầu/hint theo khả năng provider**, không phải cam kết mọi association sẽ trì hoãn theo cách giống nhau trong mọi cấu hình.

**@OneToMany** và **@ManyToMany** có mặc định LAZY, nhưng nên ghi rõ fetch trong bài học để người đọc biết ý định. Không đặt **EAGER** hàng loạt để chữa LazyInitializationException; điều đó có thể làm mọi request tải dữ liệu thừa và vẫn không bảo đảm hết N+1.

### 2.1. Owning side và mappedBy

~~~java
@Entity
class PurchaseOrder {
    @OneToMany(mappedBy = "order",
               cascade = CascadeType.ALL,
               orphanRemoval = true,
               fetch = FetchType.LAZY)
    private List<OrderLine> lines = new ArrayList<>();
}

@Entity
class OrderLine {
    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;
}
~~~

Đây là **đoạn minh họa mapping**, các class đầy đủ và imports nằm ở phần dự án. **mappedBy = "order"** tham chiếu tên **field Java** trong OrderLine, không phải cột SQL order_id. **@JoinColumn(name="order_id")** nằm ở owning side để xác định cột khóa ngoại. **optional=false** thể hiện quan hệ bắt buộc ở mô hình JPA; **nullable=false** thể hiện constraint của cột do schema generator tạo (đừng chỉ dựa vào Java check thay database constraint).

Khi chỉ thay collection ở inverse side nhưng không cập nhật OrderLine.order, trạng thái in-memory có thể lệch với FK thực tế. Vì vậy nên dùng **helper method addLine/removeLine để đồng bộ cả hai phía**.

### 2.2. Một chiều hay hai chiều?

- **Bidirectional @OneToMany/@ManyToOne** dễ đi từ cả hai hướng; muốn giữ chính xác phải cập nhật cả hai object references. Với FK tại bảng child, thường cho phép SQL UPDATE/DELETE gọn hơn khi quản lý collection.
- **Unidirectional @ManyToOne** trên child thường đơn giản: child giữ FK, không có collection trong parent; khi chỉ cần child -> parent, đây là lựa chọn tiết kiệm.
- **Unidirectional @OneToMany** chỉ có collection parent; tùy mapping/provider, Hibernate có thể dùng link table và khi sửa collection gây nhiều DELETE/INSERT join table không mong muốn. Nếu bắt buộc FK ở child, cấu hình join column cần cân nhắc và kiểm thử SQL thực.
- **@ManyToMany** phù hợp khi cả hai entity có vòng đời độc lập và quan hệ chỉ là join table. Nếu quan hệ có dữ liệu như quantity, createdAt hoặc role, nên mô hình hóa **association entity** để quản lý dễ hơn.

**Nguyên tắc:** thiết kế theo **ownership của dữ liệu và vòng đời nghiệp vụ**, không chỉ theo khả năng điều hướng object graph.

## 3. Cascade là gì? Nó không đồng nghĩa với SQL ON DELETE CASCADE

**CascadeType** định nghĩa việc một thao tác trạng thái trên entity được **lan truyền** đến các entity quan hệ thông qua JPA persistence context. Các loại:

| CascadeType | Operation JPA liên quan | Cách hiểu |
| --- | --- | --- |
| **PERSIST** | EntityManager.persist(parent) | Persist các children được tham chiếu theo association |
| **MERGE** | EntityManager.merge(parent) | Merge trạng thái entity liên quan theo quy tắc của provider |
| **REMOVE** | EntityManager.remove(parent) | Propagate remove tới child |
| **REFRESH** | EntityManager.refresh(parent) | Refresh child trong phạm vi quan hệ |
| **DETACH** | EntityManager.detach(parent) | Propagate detach |
| **ALL** | Tất cả các loại trên | Thuận tiện nhưng phạm vi rộng nhất |

**CascadeType.ALL** không phải là “mọi thứ đều tự động cập nhật đúng”. Khi **OrderLine** là phần tử sở hữu riêng của **PurchaseOrder** và không thể tồn tại độc lập, cascade ALL có thể hợp lý. Nhưng nếu **Product** hoặc **Customer** được chia sẻ bởi nhiều order, **không đặt CascadeType.REMOVE/ALL lên @ManyToOne từ OrderLine sang Product/Customer**; xóa một order line có thể kéo theo xóa shared product/customer và gây mất dữ liệu hoặc FK violations.

**Cascade PERSIST** giúp:

~~~java
PurchaseOrder order = new PurchaseOrder("PO-001");
order.addLine(new OrderLine("BOOK", 2, 100));
orderRepository.saveAndFlush(order);
~~~

Nếu mapping parent.lines có **cascade = CascadeType.PERSIST** (hoặc ALL), thao tác persist order mới sẽ lan tới line mới. Không có cascade, tùy provider và thời điểm flush, bạn phải persist line tường minh hoặc gặp lỗi transient object/FK. Trong Spring Data JPA, **save** có thể dùng **persist cho entity mới** hoặc **merge cho entity đã tồn tại/detached**; với merge, managed instance trả về có thể **khác** object đã truyền vào. Vì vậy, các test dưới đây tập trung object mới và managed entity tải lại, không suy luận rằng mọi save luôn là persist.

### 3.1. Cascade REMOVE khác SQL foreign key ON DELETE CASCADE

**CascadeType.REMOVE** là hành vi của **JPA provider khi bạn xóa entity thông qua EntityManager/repository**. **ON DELETE CASCADE** lại là rule của **database foreign key**; nó có thể hoạt động cả với SQL DELETE trực tiếp. Không coi hai cơ chế này là đồng nhất.

Các câu lệnh **bulk JPQL update/delete** hoặc native SQL thường **bỏ qua lifecycle callbacks và entity-level cascade của persistence context**. Ví dụ:

~~~java
@Modifying
@Query("delete from PurchaseOrder o where o.code = :code")
void deleteByCodeBulk(@Param("code") String code);
~~~

Đây là **trích đoạn repository method**, không nằm trong code runnable. Lệnh bulk như vậy không phải lúc nào cũng xóa child qua CascadeType.REMOVE; nếu DB còn FK, nó có thể fail. Muốn bulk delete phải thiết kế schema, thứ tự delete hoặc database cascade có chủ đích và kiểm thử trên DB thật.

### 3.2. Cascade không quyết định owning side

Một association có thể để cascade ở **inverse collection** nhưng cột FK vẫn do **@ManyToOne owning side** quyết định. Nếu helper addLine chỉ **lines.add(child)** mà quên **child.setOrder(this)**, cascade persist không bảo đảm khóa ngoại được set đúng. Trong mô hình nullable=false, có thể gặp constraint violation. **Mapping đúng phải nhất quán giữa object state và relational FK.**

## 4. Orphan removal: xóa child khi tách khỏi parent

**orphanRemoval = true** diễn tả **vòng đời phụ thuộc**: một child bị loại khỏi association được quản lý thì nó không còn “chủ sở hữu” hợp lệ, do đó JPA provider lên lịch xóa child ở database. Thuộc tính này dùng cho **@OneToMany** và **@OneToOne**, không phải một công tắc xóa chung cho @ManyToMany.

Trong ví dụ:

~~~java
PurchaseOrder managed = orderRepository.findById(id).orElseThrow();
OrderLine line = managed.getLines().get(0);
managed.removeLine(line);
entityManager.flush();
~~~

Với **orphanRemoval=true**, Hibernate sẽ phát **DELETE** tương ứng OrderLine bị remove trong flush (SQL cụ thể phụ thuộc provider/DDL/version). Nếu bỏ orphanRemoval và quan hệ cho phép null FK, việc tách con thường chỉ có ý nghĩa cập nhật hoặc xóa liên kết chứ **không mặc định xóa hàng con**. Với nullable=false, việc tách quan hệ mà không xóa child có thể vi phạm ràng buộc FK.

| Tình huống | CascadeType.REMOVE | orphanRemoval=true |
| --- | --- | --- |
| Remove parent qua EntityManager | Có thể propagate remove xuống children | Cũng thường dẫn đến xóa children được sở hữu khi parent bị remove |
| Chỉ remove một child khỏi managed collection | **Không tự động xóa child chỉ nhờ REMOVE** | **Xóa child orphan** khi flush, theo semantics association |
| Child tồn tại độc lập, có thể chuyển parent | Thường không thích hợp nếu delete parent phải giữ child | Thường **không nên bật**, vì tách parent cũ có thể xóa child |
| Đối tượng con được chia sẻ như Product/Tag | REMOVE gây nguy hiểm | Orphan removal cũng không đúng ownership |
| Thao tác bulk SQL/JPQL | Không vận hành như remove từng entity | Không nên mong nó chạy orphan check trên managed graph |

**Khác biệt ngắn gọn:** cascade REMOVE nói “khi xóa cha, lan thao tác xóa xuống con”; orphanRemoval nói “khi con rời khỏi quan hệ sở hữu, xóa con”.

### 4.1. Orphan không phải “mất hết mọi foreign key”

Trong JPA, orphan removal được xác định bởi **association đã khai báo**. Nó không phải garbage collector chạy toàn database để tìm entity không có parent. Cơ chế có điều kiện về managed/detached/new state; Jakarta Persistence không yêu cầu orphan removal áp dụng cho một entity mới chưa persist bị bỏ khỏi collection theo mọi biến thể. Đừng dựa vào orphanRemoval như quy tắc dọn rác cho mọi transient child.

**Không tái gán một child vừa bị orphan sang parent khác trong cùng unit of work** nếu aggregate semantics là xóa orphan; kết quả có thể dẫn tới entity scheduled for deletion/constraint exception. Nếu business thực sự yêu cầu di chuyển line giữa hai order, phải thiết kế lifecycle khác, không dùng orphanRemoval mù quáng.

### 4.2. Không thay hẳn collection reference vô tội vạ

Với Hibernate-managed persistent collection, thay:

~~~java
managedOrder.setLines(new ArrayList<>(newLines));
~~~

có thể làm wrapper collection gốc bị mất reference và dẫn tới lỗi hoặc xóa không đúng ý định khi có orphanRemoval. Trong ví dụ đầy đủ, ta **không expose setter thay cả collection**, mà giữ một **final List** và chỉ thay đổi qua addLine/removeLine, giữ đồng bộ hai phía. Nếu cần cập nhật một danh sách theo payload, hãy diff các child đang managed theo id/business key rồi add/remove có chủ đích.

## 5. LAZY loading: lúc nào có SQL và khi nào ném lỗi?

**FetchType.LAZY** nghĩa là provider cố gắng trì hoãn tải association tới khi thật sự cần. Với Hibernate, collection thường là một **persistent collection wrapper**; to-one có thể là proxy hoặc enhanced entity. Một entity loaded qua repository chỉ mới có các scalar fields và một tham chiếu lazy, chưa nhất thiết query toàn bộ children.

~~~text
repository.findById(orderId)
   |
   +-- SQL SELECT purchase_orders ...
   |
   +-- order.getLines()  -> persistent collection chưa initialized
          |
          +-- order.getLines().size() khi session còn mở
                 -> SQL SELECT order_lines WHERE order_id=?
                 -> collection initialized
~~~

Khi **EntityManager/Session đã đóng hoặc entity bị detach** trước khi collection được initialize:

~~~java
PurchaseOrder detached = orderRepository.findById(id).orElseThrow();
entityManager.detach(detached);
detached.getLines().size(); // Có thể ném LazyInitializationException
~~~

Đoạn này cần bối cảnh có một order đã lưu, persistence context vẫn còn ở thời điểm detach; phần 9 có test đầy đủ. **LazyInitializationException** của Hibernate xảy ra khi một lazy proxy/collection chưa initialized được truy cập mà không còn session thích hợp. **Không phải cứ có @Transactional là mọi lazy loading đều thành công**: transaction phải còn bao quanh **lúc dữ liệu được truy cập**, và entity/proxy phải thuộc persistence context tương ứng.

### 5.1. Test slice @DataJpaTest có thể che lỗi LAZY trong production

**@DataJpaTest mặc định mở transaction và rollback cuối mỗi test method**. Vì vậy:

~~~java
@DataJpaTest
class MappingTest {
    @Test
    void test() {
        PurchaseOrder order = orders.findById(id).orElseThrow();
        order.getLines().size(); // Có thể thành công vì test transaction đang mở.
    }
}
~~~

Không được suy ra endpoint REST của production chắc chắn serialize lazy collection thành công. Khi controller trả entity sau khi service transaction đã kết thúc và **Open Session in View** bị tắt, serializer truy cập collection chưa load có thể ném LazyInitializationException. Nếu Open Session in View bật, nó có thể cho phép lazy query ngoài service transaction, gây SQL ở tầng HTTP serialization và N+1 khó kiểm soát.

**Giải pháp có chủ đích:** tại service transaction, fetch đúng dữ liệu cần thiết rồi **map sang DTO**. Đừng trả nguyên entity JPA có graph hai chiều ra JSON chỉ để tiện; ngoài lỗi lazy, còn rủi ro recursive serialization parent ↔ children và lộ dữ liệu không cần thiết.

### 5.2. Hibernate.isInitialized và EntityManager.clear

Trong test cần xác nhận lazy state trực tiếp:

~~~java
entityManager.flush();
entityManager.clear();

PurchaseOrder reloaded = orders.findById(orderId).orElseThrow();
assertFalse(Hibernate.isInitialized(reloaded.getLines()));

int count = reloaded.getLines().size();
assertEquals(2, count);
assertTrue(Hibernate.isInitialized(reloaded.getLines()));
~~~

**flush** đẩy những SQL changes đang pending xuống database trong transaction hiện tại; **clear** tách toàn bộ managed entities khỏi persistence context để lần findById sau không chỉ trả object đã cache level 1. Nếu không clear, bạn có thể nhận lại cùng parent/children đã được initialize từ lúc tạo, khiến assertion LAZY không có giá trị.

**flush không phải commit.** @DataJpaTest transaction vẫn rollback cuối method. Vì vậy query sau clear đọc được bản ghi đã flush **trong cùng transaction**, không phải bằng chứng thay đổi đã commit để process khác thấy.

## 6. N+1 queries: tại sao mỗi order lại gây một SELECT?

Giả sử repository đọc **N orders**:

~~~java
List<PurchaseOrder> orders = repository.findAll();
for (PurchaseOrder order : orders) {
    System.out.println(order.getLines().size());
}
~~~

Nếu collection lines đang LAZY và chưa initialized, Hibernate có thể thực hiện:

~~~sql
SELECT ... FROM purchase_orders;                 -- 1 query
SELECT ... FROM order_lines WHERE order_id = ?;  -- order 1
SELECT ... FROM order_lines WHERE order_id = ?;  -- order 2
SELECT ... FROM order_lines WHERE order_id = ?;  -- order 3
-- ...
~~~

**N+1** là một query lấy N parents cộng tới N queries lấy associations. Đây là **mô hình thường gặp**, không bảo đảm mọi provider hay cấu hình đều dùng đúng N+1 SQL: cache, batching, subselect fetch, first-level context và join plans có thể thay đổi số lượng thực. Nhưng nó là cảnh báo rằng chi phí đọc association có thể tăng theo số parents.

**Không chữa bằng cách chuyển toàn bộ quan hệ thành FetchType.EAGER**. EAGER có thể nạp dữ liệu thừa ở các use case khác và một số query vẫn phải sử dụng secondary SELECT. Cần **query-specific fetch plan** cho những nơi biết trước sẽ dùng children.

### 6.1. Spring Data JPA @EntityGraph

~~~java
@EntityGraph(attributePaths = "lines")
@Query("select o from PurchaseOrder o where o.id = :id")
Optional<PurchaseOrder> findDetailById(@Param("id") Long id);
~~~

**@EntityGraph** yêu cầu association lines được fetch cùng truy vấn theo fetch graph của JPA provider; Hibernate thường chọn JOIN cho collection đơn giản, nhưng **không dựa vào một mẫu SQL cố định** khi test behavior. EntityGraph hợp với repository method riêng cho màn hình order detail.

### 6.2. JPQL JOIN FETCH

~~~java
@Query("""
    select distinct o
    from PurchaseOrder o
    left join fetch o.lines
    where o.id = :id
    """)
Optional<PurchaseOrder> findDetailWithJoinFetch(@Param("id") Long id);
~~~

Đây là phương án tường minh yêu cầu fetch association. Với collection, nhiều hàng SQL có thể thuộc cùng một order; **distinct** thể hiện ý định tránh duplicate parent ở kết quả object, còn Hibernate 6 có một số cơ chế deduplicate tự động. SQL và hành vi DISTINCT có thể phụ thuộc provider/query plan. Không viết test đoán đúng số dòng SQL từ ví dụ giản lược.

**Cảnh báo pagination:** join fetch collection rồi phân trang theo database có thể bị phân trang trong memory hoặc đưa ra warning/failure tùy cấu hình. Khi đọc trang nhiều parents có children, thường cần **hai bước**: page IDs/parents trước, rồi query fetch children theo danh sách IDs, hoặc dùng DTO projection/batch fetch phù hợp. Không áp dụng một JOIN FETCH collection bừa bãi cho mọi PageRequest.

### 6.3. Batch fetching và DTO projection

Hibernate hỗ trợ **hibernate.default_batch_fetch_size** hoặc **@BatchSize** để giảm số truy vấn khi initialize nhiều lazy associations, tùy access pattern và provider configuration. Đây là kỹ thuật **tối ưu** chứ không thay yêu cầu transaction và fetch đúng dữ liệu.

**DTO projection** chỉ lấy các scalar fields cần cho response (code, SKU, quantity…), tránh load toàn bộ object graph. Khi cần một màn hình danh sách orders chỉ hiển thị code và số items, có thể dùng aggregate count query thay vì fetch mọi line. Đo query count bằng Hibernate statistics/SQL logging hoặc datasource proxy trong integration/performance test, không khẳng định một query luôn nhanh hơn trong mọi database.

## 7. Dự án runnable: Spring Boot 3.4.5 + H2 + JUnit

Tất cả các source files dưới đây tạo thành một dự án nhỏ. Nó có **parent PurchaseOrder** và **child OrderLine**, mapping hai chiều, cascade ALL trên parent collection, orphanRemoval=true và LAZY. Test sử dụng @DataJpaTest, repository, EntityManager và Hibernate.isInitialized.

**Quy tắc nghiệp vụ demo:**

- Mỗi PurchaseOrder có **code** duy nhất và một hoặc nhiều OrderLine.
- Mỗi OrderLine có **sku, quantity, unitPrice** và FK bắt buộc đến một order.
- OrderLine **không tồn tại độc lập**; khi xóa order, lines được xóa theo; khi remove line khỏi managed order, orphanRemoval xóa row line.
- Java helper cập nhật cả **order.getLines()** và **line.getOrder()**.
- Repository có method bình thường (LAZY) và một method **@EntityGraph** dành cho chi tiết.
- Test xác nhận **cascade persist, FK, orphan deletion, cascade remove, LAZY loading, detached failure và fetch graph**.

### 7.1. Cấu trúc file

~~~text
settings.gradle
build.gradle
src/main/resources/application.yml
src/main/java/com/example/jparel/JpaRelationshipApplication.java
src/main/java/com/example/jparel/PurchaseOrder.java
src/main/java/com/example/jparel/OrderLine.java
src/main/java/com/example/jparel/PurchaseOrderRepository.java
src/main/java/com/example/jparel/OrderLineRepository.java
src/test/java/com/example/jparel/PurchaseOrderMappingTest.java
src/test/java/com/example/jparel/PurchaseOrderLazyLoadingTest.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'jpa-relationship-mapping-tests'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.4.5'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    runtimeOnly 'com.h2database:h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Spring Boot BOM quản lý Hibernate/Spring Data JPA/JUnit. Không tự ép các phiên bản Jakarta Persistence và Hibernate khác dòng chỉ để dùng annotation. H2 được chọn để không cần database bên ngoài và chạy @DataJpaTest nhanh; khi SQL dialect/lock/isolation/schema migration là đối tượng kiểm thử, dùng Testcontainers và engine gần production thay vì chỉ H2.

**src/main/resources/application.yml**

~~~yaml
spring:
  datasource:
    generate-unique-name: true
  jpa:
    hibernate:
      ddl-auto: create-drop
    open-in-view: false
  sql:
    init:
      mode: never
~~~

**ddl-auto=create-drop** giúp dựng schema học tập từ entity ở context JPA; không dùng nguyên trạng cho production, nơi cần versioned migrations. **open-in-view=false** minh họa ranh giới persistence rõ trong web app, nhưng không tự loại transaction do @DataJpaTest mở. **generate-unique-name** giảm nguy cơ các ApplicationContexts H2 in-memory khác nhau dùng trùng tên DB. **sql.init.mode=never** tránh script SQL init ngoài ý muốn trong demo.

### 7.2. Application class

**src/main/java/com/example/jparel/JpaRelationshipApplication.java**

~~~java
package com.example.jparel;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JpaRelationshipApplication {
    public static void main(String[] args) {
        SpringApplication.run(JpaRelationshipApplication.class, args);
    }
}
~~~

### 7.3. Parent entity: quản lý collection qua helpers

**src/main/java/com/example/jparel/PurchaseOrder.java**

~~~java
package com.example.jparel;

import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

import jakarta.persistence.CascadeType;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.OneToMany;
import jakarta.persistence.Table;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "order_code", nullable = false, unique = true)
    private String code;

    @OneToMany(
            mappedBy = "order",
            cascade = CascadeType.ALL,
            orphanRemoval = true,
            fetch = FetchType.LAZY)
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {
        // Required by JPA.
    }

    public PurchaseOrder(String code) {
        this.code = Objects.requireNonNull(code, "code");
    }

    public Long getId() {
        return id;
    }

    public String getCode() {
        return code;
    }

    public List<OrderLine> getLines() {
        return lines;
    }

    public void addLine(OrderLine line) {
        Objects.requireNonNull(line, "line");
        if (line.getOrder() != null) {
            throw new IllegalStateException(
                    "line is already assigned to an order");
        }
        lines.add(line);
        line.setOrder(this);
    }

    public void removeLine(OrderLine line) {
        if (lines.remove(line)) {
            line.setOrder(null);
        }
    }
}
~~~

**Vì sao không có setLines?** Persistence provider cần theo dõi wrapper collection và orphan state. Giữ nguyên collection, chỉ add/remove có kiểm soát, giúp tránh vô tình thay reference. Ví dụ trả trực tiếp List để đơn giản hóa test; ở API production cần tránh cho caller tự **getLines().clear()** hoặc add mà không đồng bộ owning side. Có thể expose immutable view riêng cho business callers và giữ method mutation có chủ đích, miễn không làm test Hibernate.isInitialized trên một wrapper khác wrapper gốc.

**Không dùng Lombok @Data/toString()/equals/hashCode tự sinh trên toàn bộ association**: dễ gây đệ quy parent↔child, kích hoạt LAZY loading ngoài ý muốn, hoặc làm hashCode thay đổi khi @GeneratedValue cấp ID. Nếu cần equality cho entity, chọn immutable natural key hoặc chiến lược ID nhất quán, kiểm tra proxy/lifecycle và tránh đưa association vào equals/hashCode.

### 7.4. Child entity: FK và owning side

**src/main/java/com/example/jparel/OrderLine.java**

~~~java
package com.example.jparel;

import java.util.Objects;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;

@Entity
@Table(name = "order_lines")
public class OrderLine {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String sku;

    @Column(nullable = false)
    private int quantity;

    @Column(name = "unit_price", nullable = false)
    private int unitPrice;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    protected OrderLine() {
        // Required by JPA.
    }

    public OrderLine(String sku, int quantity, int unitPrice) {
        this.sku = Objects.requireNonNull(sku, "sku");
        if (quantity <= 0 || unitPrice < 0) {
            throw new IllegalArgumentException(
                    "invalid quantity or unit price");
        }
        this.quantity = quantity;
        this.unitPrice = unitPrice;
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public int getQuantity() {
        return quantity;
    }

    public int getUnitPrice() {
        return unitPrice;
    }

    public PurchaseOrder getOrder() {
        return order;
    }

    void setOrder(PurchaseOrder order) {
        this.order = order;
    }
}
~~~

**FK thật** được ánh xạ qua **@JoinColumn(name="order_id")** ở OrderLine.order. **fetch=LAZY** có chủ ý để tránh tải parent khi chỉ cần dữ liệu line. Child không có cascade từ nó lên PurchaseOrder, vì xóa một line không nên xóa order. **optional=false/nullable=false** nhấn mạnh child không được tồn tại không có order; lúc removeLine, orphanRemoval sẽ xóa child ở flush thay vì lưu một FK NULL.

Đây là aggregate với child không được chia sẻ. Nếu OrderLine có quyền sống độc lập hoặc chuyển order, cần thiết kế lại nullable/orphan policy.

### 7.5. Repositories: bình thường và fetch graph

**src/main/java/com/example/jparel/PurchaseOrderRepository.java**

~~~java
package com.example.jparel;

import java.util.List;
import java.util.Optional;

import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @EntityGraph(attributePaths = "lines")
    @Query("select o from PurchaseOrder o where o.id = :id")
    Optional<PurchaseOrder> findDetailById(@Param("id") Long id);

    @EntityGraph(attributePaths = "lines")
    @Query("select distinct o from PurchaseOrder o")
    List<PurchaseOrder> findAllWithLines();
}
~~~

**@EntityGraph(attributePaths="lines")** dành cho các use case cần dữ liệu lines. Repository kế thừa **findById** và **findAll** thông thường không bắt buộc fetch lines chỉ vì class có getLines(). Tách hai query methods giúp contract performance rõ ràng: bản danh sách chỉ cần order code không phải trả hết lines, còn bản chi tiết mới cần collection.

**src/main/java/com/example/jparel/OrderLineRepository.java**

~~~java
package com.example.jparel;

import org.springframework.data.jpa.repository.JpaRepository;

public interface OrderLineRepository
        extends JpaRepository<OrderLine, Long> {
}
~~~

Repository thứ hai chỉ để test **count/existsById** trên bảng con sau flush/clear. Không phải mọi ứng dụng cần public repository cho aggregate child; khi design domain nghiêm ngặt, có thể giữ thao tác ghi child chỉ thông qua aggregate root repository và dùng EntityManager/JDBC cho test verification.

## 8. @DataJpaTest: xác nhận cascade và orphan removal bằng database thật

**src/test/java/com/example/jparel/PurchaseOrderMappingTest.java**

~~~java
package com.example.jparel;

import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@DataJpaTest
class PurchaseOrderMappingTest {

    @Autowired
    private PurchaseOrderRepository orders;

    @Autowired
    private OrderLineRepository lines;

    @PersistenceContext
    private EntityManager entityManager;

    @Test
    void cascadePersistSavesBothChildrenAndForeignKeys() {
        PurchaseOrder order = new PurchaseOrder("PO-CASCADE");
        order.addLine(new OrderLine("BOOK", 2, 100));
        order.addLine(new OrderLine("PEN", 3, 20));

        orders.saveAndFlush(order);
        Long orderId = order.getId();
        assertNotNull(orderId);

        entityManager.clear();

        PurchaseOrder reloaded =
                orders.findById(orderId).orElseThrow();
        assertEquals("PO-CASCADE", reloaded.getCode());
        assertEquals(2, reloaded.getLines().size());
        assertEquals(2L, lines.count());

        for (OrderLine line : reloaded.getLines()) {
            assertNotNull(line.getId());
            assertEquals(orderId, line.getOrder().getId());
        }
    }

    @Test
    void removingOneManagedChildDeletesOnlyThatOrphan() {
        PurchaseOrder order = new PurchaseOrder("PO-ORPHAN");
        order.addLine(new OrderLine("BOOK", 1, 100));
        order.addLine(new OrderLine("PEN", 1, 20));

        orders.saveAndFlush(order);
        Long orderId = order.getId();
        entityManager.clear();

        PurchaseOrder managed =
                orders.findById(orderId).orElseThrow();
        OrderLine removed = managed.getLines().stream()
                .filter(line -> line.getSku().equals("BOOK"))
                .findFirst().orElseThrow();
        Long removedId = removed.getId();

        managed.removeLine(removed);
        entityManager.flush();
        entityManager.clear();

        assertFalse(lines.existsById(removedId));
        PurchaseOrder stillExists =
                orders.findById(orderId).orElseThrow();
        assertEquals(1, stillExists.getLines().size());
        assertEquals("PEN",
                stillExists.getLines().get(0).getSku());
    }

    @Test
    void deletingParentAlsoRemovesOwnedChildren() {
        PurchaseOrder order = new PurchaseOrder("PO-REMOVE");
        order.addLine(new OrderLine("A", 1, 10));
        order.addLine(new OrderLine("B", 1, 15));

        orders.saveAndFlush(order);
        Long orderId = order.getId();
        entityManager.clear();

        PurchaseOrder managed =
                orders.findById(orderId).orElseThrow();
        orders.delete(managed);
        entityManager.flush();
        entityManager.clear();

        assertFalse(orders.existsById(orderId));
        assertEquals(0L, lines.count());
    }

    @Test
    void deletingNoOrphansWhenAssociationUnchanged() {
        PurchaseOrder order = new PurchaseOrder("PO-KEEP");
        order.addLine(new OrderLine("KEEP", 1, 10));

        orders.saveAndFlush(order);
        Long lineId = order.getLines().get(0).getId();
        entityManager.clear();

        PurchaseOrder managed =
                orders.findById(order.getId()).orElseThrow();
        assertEquals(1, managed.getLines().size());
        entityManager.flush();
        entityManager.clear();

        assertTrue(lines.existsById(lineId));
    }
}
~~~

**Bốn phép thử và ý nghĩa:**

1. **cascadePersistSavesBothChildrenAndForeignKeys:** chỉ save **PurchaseOrder mới**, cascade ALL propagate persist tới hai OrderLine. Sau **flush + clear**, lấy lại từ H2, đếm child rows và kiểm tra mỗi child mang FK đúng parent. Điều này mạnh hơn chỉ nhìn Java collection đã add.
2. **removingOneManagedChildDeletesOnlyThatOrphan:** tải parent thành managed entity, loại một line bằng helper, flush + clear, kiểm tra row BOOK **thật sự biến mất**, parent vẫn còn và line PEN vẫn tồn tại. Nếu thiếu orphanRemoval, test thường fail hoặc gặp FK semantics khác.
3. **deletingParentAlsoRemovesOwnedChildren:** xóa parent qua repository/EntityManager, cascade REMOVE từ ALL dẫn tới child deletion. Bài test không dùng JPQL bulk delete, vì bulk có semantics khác.
4. **deletingNoOrphansWhenAssociationUnchanged:** chỉ tải/flush association không thay đổi; orphan removal không phải cơ chế tự xóa mọi child sau mỗi lần flush.

**@DataJpaTest** mở transaction cho từng test method và **rollback cuối method**. Mỗi test ở class này độc lập nhờ transaction rollback, dù cùng Spring test context có thể được cache. Để kiểm tra **SQL thật sự được gửi**, dùng **saveAndFlush** và **entityManager.flush**; không nhầm flush với commit. **entityManager.clear** buộc lần đọc sau truy vấn lại, tránh chỉ quan sát first-level cache.

Trong ví dụ không khai báo SQL stdout cụ thể, vì thứ tự SQL INSERT/DELETE có thể phụ thuộc Hibernate và ID generation. Kết quả được xác minh bằng assertions về **rows, IDs, FK và surviving parent**, không phụ thuộc log.

## 9. @DataJpaTest: kiểm chứng lazy state, detached error và @EntityGraph

**src/test/java/com/example/jparel/PurchaseOrderLazyLoadingTest.java**

~~~java
package com.example.jparel;

import java.util.List;

import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;

import org.hibernate.Hibernate;
import org.hibernate.LazyInitializationException;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@DataJpaTest
class PurchaseOrderLazyLoadingTest {

    @Autowired
    private PurchaseOrderRepository orders;

    @PersistenceContext
    private EntityManager entityManager;

    private Long createOrder(String code, int count) {
        PurchaseOrder order = new PurchaseOrder(code);
        for (int i = 0; i < count; i++) {
            order.addLine(
                    new OrderLine("SKU-" + i, 1, 10 + i));
        }
        orders.saveAndFlush(order);
        Long id = order.getId();
        entityManager.clear();
        return id;
    }

    @Test
    void collectionLoadsOnlyWhenAccessedInsideSession() {
        Long id = createOrder("PO-LAZY", 2);
        PurchaseOrder loaded =
                orders.findById(id).orElseThrow();

        assertFalse(Hibernate.isInitialized(loaded.getLines()));

        assertEquals(2, loaded.getLines().size());
        assertTrue(Hibernate.isInitialized(loaded.getLines()));
    }

    @Test
    void detachedUninitializedCollectionFailsOnAccess() {
        Long id = createOrder("PO-DETACH", 1);
        PurchaseOrder loaded =
                orders.findById(id).orElseThrow();

        assertFalse(Hibernate.isInitialized(loaded.getLines()));
        entityManager.detach(loaded);

        assertThrows(LazyInitializationException.class,
                () -> loaded.getLines().size());
    }

    @Test
    void entityGraphLoadsCollectionBeforeDetach() {
        Long id = createOrder("PO-DETAIL", 2);
        PurchaseOrder detail =
                orders.findDetailById(id).orElseThrow();

        assertTrue(Hibernate.isInitialized(detail.getLines()));
        entityManager.detach(detail);

        assertEquals(2, detail.getLines().size());
    }

    @Test
    void entityGraphCanFetchCollectionsForMultipleParents() {
        createOrder("PO-LIST-1", 1);
        createOrder("PO-LIST-2", 2);

        List<PurchaseOrder> result = orders.findAllWithLines();
        assertEquals(2, result.size());
        assertTrue(result.stream()
                .allMatch(order ->
                    Hibernate.isInitialized(order.getLines())));
    }
}
~~~

### 9.1. Test LAZY đầu tiên kiểm chứng điều gì?

**collectionLoadsOnlyWhenAccessedInsideSession** tạo dữ liệu, flush/clear, load parent từ repository. Collection chưa initialize nên Hibernate.isInitialized trả false; khi gọi size() bên trong @DataJpaTest transaction, Hibernate có session để tải lines, rồi flag thành true. Đây là **behavioral assertion**, không đoán SQL chỉ dựa vào tên LAZY.

**detachedUninitializedCollectionFailsOnAccess** cho parent detach khỏi persistence context **trước khi** collection được truy cập. Hibernate không còn session phù hợp cho lazy initialization, vì vậy size() ném **LazyInitializationException**. Điểm cốt lõi: ngay cả khi test method vẫn có transaction, **đối tượng đã detach** không còn managed; một transaction khác tồn tại không tự động nối lại nó.

**entityGraphLoadsCollectionBeforeDetach** dùng repository method có @EntityGraph. Hibernate đã khởi tạo lines trong query trước khi detach; vì vậy size() vẫn đọc được collection đã initialize sau detach. Lưu ý điều này **không bảo đảm các association lồng sâu trong OrderLine cũng đã initialize**; fetch graph chỉ mô tả paths được yêu cầu.

**entityGraphCanFetchCollectionsForMultipleParents** tạo hai orders trong cùng test, dùng repository method fetch graph rồi assert collections đã initialize. Nó **không assert số SQL statements** vì provider/config có thể khác; nếu hiệu năng N+1 là requirement, bổ sung Hibernate statistics/SQL metrics một cách độc lập.

### 9.2. Vì sao không dùng assertThrows với repository.findById đơn giản?

Repository.findById có thể hoạt động và trả parent thành công; lỗi LAZY thường chỉ xuất hiện **khi chạm association chưa initialize** sau persistence context boundary. Viết assertThrows(LazyInitializationException.class, () -> repository.findById(id)) thường kiểm tra sai điểm phát sinh lỗi. Phải sắp đặt **flush/clear, findById, kiểm tra chưa initialize, detach, rồi mới truy cập collection**.

### 9.3. Điều kiện ảnh hưởng kết quả test

Test giả định Hibernate 6.6.x với **LAZY collection**, H2 và không cấu hình đặc biệt như enable_lazy_load_no_trans hoặc global fetch profile kéo lines theo parent. Nếu project bật extra-lazy, eager graph, bytecode enhancement, caching hoặc OSIV khác demo, behavior chi tiết có thể thay đổi. Test cần xác nhận **contract của dự án**, không cố buộc mọi mapping dùng Hibernate đúng một câu SQL.

## 10. Chạy ví dụ và cách đọc kết quả

Với Gradle Wrapper tương thích JDK 17 và Spring Boot 3.4.5 tại thư mục root:

~~~bash
./gradlew clean test
./gradlew test --tests com.example.jparel.PurchaseOrderMappingTest
./gradlew test --tests com.example.jparel.PurchaseOrderLazyLoadingTest
~~~

Trên Windows dùng **gradlew.bat** cùng các tham số. Các test được **thiết kế để PASS** với files và dependencies như trên. Đây là kết quả **kỳ vọng suy ra từ mã**, không phải stdout Gradle đã được chạy thực tế. Có thể bật Hibernate SQL logging để thấy queries, nhưng đừng sao chép một SQL trace làm output bắt buộc trên mọi version.

Kết quả dự kiến theo assertions:

| Test | Bằng chứng mong đợi |
| --- | --- |
| cascadePersistSavesBothChildrenAndForeignKeys | Parent và 2 child rows tồn tại; child FK trỏ parent |
| removingOneManagedChildDeletesOnlyThatOrphan | Child BOOK bị xóa; parent cùng child PEN vẫn còn |
| deletingParentAlsoRemovesOwnedChildren | Xóa parent xóa cả 2 children qua entity-level cascade |
| deletingNoOrphansWhenAssociationUnchanged | Không có child row bị xóa nếu collection không đổi |
| collectionLoadsOnlyWhenAccessedInsideSession | Collection chưa initialize trước size(), initialized sau size() |
| detachedUninitializedCollectionFailsOnAccess | LazyInitializationException khi truy cập detached lazy collection |
| entityGraphLoadsCollectionBeforeDetach | Collection đã initialize, đọc được sau detach |
| entityGraphCanFetchCollectionsForMultipleParents | Cả hai parent có collection đã initialize theo fetch graph |

**Không dùng test xanh này để khẳng định production DB engine, transaction isolation, connection pool hoặc API serialization đã đúng**. H2 có thể khác PostgreSQL/MySQL/Oracle về SQL dialect, FK behavior, locking và migration. Nếu feature phụ thuộc vendor-specific SQL hoặc constraint, chạy @DataJpaTest với Testcontainers/datasource cùng engine và quản lý cleanup đúng cách.

## 11. Transaction và flush: quan sát thay đổi ở đúng thời điểm

Trong JPA, có thể tách ba khái niệm:

- **Persist/dirty checking:** đánh dấu entity state thay đổi trong persistence context.
- **Flush:** đồng bộ những thay đổi pending thành SQL trong transaction; phát hiện nhiều mapping/constraint violations tại đây.
- **Commit:** transaction hoàn tất và dữ liệu trở nên durable/visible theo isolation rules; @DataJpaTest mặc định **rollback**, không commit.

Ví dụ một test chỉ kiểm tra Java collection:

~~~java
PurchaseOrder order = new PurchaseOrder("PO-TEST");
order.addLine(new OrderLine("A", 1, 10));
assertEquals(1, order.getLines().size());
~~~

đó chỉ là **unit assertion của Java helper**, không chứng minh cascade hay FK. Muốn chứng minh mapping, dùng **saveAndFlush**, **clear**, **reload**, rồi assert dữ liệu.

Với orphan removal, tác động DELETE thường được thực hiện trong **flush**, không nhất thiết ngay lúc List.remove gọi. Nếu test chỉ xem collection length sau remove, nó có thể xanh dù orphanRemoval=false. Phải assert **OrderLineRepository.existsById(removedId) == false** sau flush/clear.

### 11.1. Khi nào dùng TestEntityManager?

Spring Boot @DataJpaTest có thể cung cấp **TestEntityManager** làm helper persist/flush/clear, song một **EntityManager @PersistenceContext** bình thường đủ cho các test trong bài. Dùng một công cụ thống nhất để không nhầm TestEntityManager với persistence context của một transaction khác. TestEntityManager không làm transaction tự commit; nó cũng không thay thế kiểm thử database schema thật.

### 11.2. Bulk delete và orphan removal

Bulk JPQL/native delete không tương đương từng lượt repository.delete(managedEntity). Những bulk operations có thể bypass entity lifecycle callbacks, cascade và persistence context state. Nếu cần xóa hàng loạt orders, hãy cân nhắc child rows, DB FK on-delete cascade, câu lệnh riêng hoặc schema design, rồi viết integration test cho đường đó. Không suy ra cascade ALL trên entity collection tự giải quyết toàn bộ bulk SQL.

## 12. Mẫu service transaction và DTO để tránh lazy lỗi ở HTTP

Một service tốt nên quyết định **đúng dữ liệu cần đọc trong một transaction** và trả **DTO**, thay vì trả entity trực tiếp cho Jackson sau transaction:

~~~java
@Service
class OrderViewService {
    private final PurchaseOrderRepository repository;

    OrderViewService(PurchaseOrderRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public OrderView detail(Long id) {
        PurchaseOrder order = repository.findDetailById(id)
                .orElseThrow();

        List<LineView> lines = order.getLines().stream()
                .map(line -> new LineView(
                        line.getSku(),
                        line.getQuantity(),
                        line.getUnitPrice()))
                .toList();

        return new OrderView(order.getCode(), lines);
    }

    record LineView(String sku, int quantity, int unitPrice) {}
    record OrderView(String code, List<LineView> lines) {}
}
~~~

Đây là **trích đoạn kiến trúc**, không thuộc cây files runnable ở phần 7, và cần imports Spring @Service, @Transactional và List. Nó minh họa:
- @Transactional(readOnly=true) giữ persistence context để phục vụ query/read mapping trong service.
- findDetailById yêu cầu lines load theo use case; giảm khả năng N+1/LAZY access ngoài service.
- DTO record không giữ Hibernate proxy hoặc collection wrapper.
- Controller có thể serialize DTO khi service transaction đã đóng mà không kích hoạt lazy query.

**readOnly=true** chỉ là optimization/hint cho transaction và provider, **không phải security guard** ngăn mọi thao tác ghi. Đừng coi read-only transaction là cơ chế phân quyền.

**Open Session in View (OSIV)**: trong web application, bật OSIV có thể cho phép lazy loading trong view serialization sau service call, nhưng điều đó che ranh giới và có thể sinh SQL ngoài business transaction. Mẫu YAML đặt **spring.jpa.open-in-view=false** để khuyến khích fetch rõ trong service.

## 13. Mapping khác: OneToOne, ManyToMany và shared entities

### 13.1. @OneToOne với orphan removal

Một Account có AccountSettings sở hữu riêng; nếu settings bị thay/xóa và không còn ý nghĩa độc lập, **@OneToOne(orphanRemoval=true)** có thể phù hợp. Nhưng mapping one-to-one bidirectional LAZY, shared primary key và unique FK có những yêu cầu proxy/enhancement khác nhau. Hãy test việc replace/remove object bằng **flush/clear** và kiểm tra row thực, đừng chỉ assert reference ở Java.

### 13.2. @ManyToMany không cascade REMOVE tới shared target

Ví dụ Student ↔ Course dùng chung Course giữa nhiều students. Nếu thêm **cascade=ALL** từ student tới courses, xóa một student có thể cố xóa Course vẫn được người khác tham chiếu, gây mất dữ liệu hoặc FK violation. Thường chỉ cần xóa row trong join table; không xóa Course. Nếu relation có thuộc tính enrollmentDate/status/grade, mô hình **Enrollment** làm entity riêng với **@ManyToOne** tới Student và Course, và cho Student sở hữu **@OneToMany<Enrollment>** nếu đúng lifecycle.

### 13.3. Child có thể chuyển từ parent A sang B

Với orphanRemoval=true, phép removeLine từ A là thông điệp “hãy xóa child”, không phải “giữ child để gán cho B”. Nếu nghiệp vụ cần chuyển một line, phải quyết định semantics riêng (không orphanRemoval, FK nullable/constraints hợp lý, hoặc thao tác lifecycle rõ với transaction), rồi kiểm thử trạng thái sau flush trên database. **Không tái sử dụng helper ownership của aggregate A sang một mô hình shared entity mà không xem lại policy.**

### 13.4. @Embeddable vs entity con

Nếu child không có danh tính độc lập, có thể cân nhắc **@Embeddable + @ElementCollection** cho value objects. Tuy nhiên ElementCollection cũng có lifecycle/fetch/update semantics riêng và có thể tốn nhiều SQL khi sửa collection. Không mặc định thay mọi OneToMany bằng ElementCollection; chọn theo identity/domain behavior.

## 14. Các lỗi thường gặp và hướng giải quyết

| Dấu hiệu | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| FK order_id NULL khi insert line | Chỉ add vào inverse collection, quên set child.order | Helper đồng bộ cả hai phía, kiểm tra nullable FK |
| OrderLine không được lưu khi save parent | Không có cascade PERSIST hoặc parent/child state khác dự kiến | Chọn cascade theo lifecycle, kiểm tra persist vs merge |
| Xóa line khỏi List nhưng row vẫn tồn tại | Chỉ có cascade REMOVE, không có orphanRemoval | Nếu child thuộc sở hữu riêng, bật orphanRemoval và flush |
| Delete parent làm xóa Product/Customer chung | CascadeType.REMOVE/ALL đặt vào shared @ManyToOne | Loại REMOVE từ association shared, kiểm tra dữ liệu còn |
| Remove child gây constraint error | FK nullable=false nhưng không xóa/không update quan hệ hợp lệ | Xác định orphan removal hoặc policy unlink |
| LazyInitializationException lúc JSON serialize | Controller trả detached entity/collection LAZY | Fetch graph trong transaction, map DTO, tránh entity serialization |
| @DataJpaTest xanh nhưng controller hỏng | Test transaction giữ session mở, web context khác | Test service/API transaction boundary riêng |
| N+1 khi hiển thị danh sách | Mỗi parent truy cập lazy children | Projection, EntityGraph, join fetch theo use case, batch fetch |
| EAGER vẫn có N+1 | Provider thực hiện secondary SELECTs hoặc query shape khác | Tối ưu query plan, đo SQL thay vì dựa vào EAGER |
| JOIN FETCH collection + Pageable cảnh báo | Collection joins nhân số hàng, pagination không đúng SQL-level | 2-step pagination hoặc projection |
| @ManyToMany delete gây FK violation | Cascade REMOVE vào shared target | Chỉ xóa join rows; dùng association entity |
| @OneToOne LAZY vẫn query sớm | Proxy/optional/inverse mapping hoặc bytecode enhancement constraints | Kiểm tra Hibernate behavior và entity design |
| Test số lines đúng nhưng DB sai | Assert Java collection, không flush/clear/reload | Kiểm tra dữ liệu sau SQL flush |
| Entity Graph test sai khi context đã cache entity | L1 cache chứa parent đã initialize | entityManager.clear() trước query cần kiểm chứng |
| equals/toString gây stack overflow | Parent↔child recursion hoặc lazy association | Không đưa relation vào generated equals/hashCode/toString |
| Bulk delete không chạy cascade | Bulk JPQL/SQL bypass entity remove semantics | Dùng DB cascade/safe delete order và integration test |
| Mỗi test chậm do nhiều Spring contexts | @SpringBootTest thay vì @DataJpaTest, cache keys biến thể | Slice test cho JPA, integration test khi cần multi-layer |
| H2 xanh, production DB fail | Dialect, constraint, isolation, migration khác | Testcontainers với engine production cho tính năng rủi ro |

## 15. Chiến lược kiểm thử đầy đủ hơn

Một bộ test cho quan hệ JPA nên có các mức:

1. **Unit test helper**: addLine/removeLine cập nhật cả hai phía và cấm reparent sai lifecycle; không cần Spring context.
2. **@DataJpaTest**: cascade persist, owning FK, orphan delete, cascade remove, lazy initialized/detached, entity graph; dùng flush/clear/reload.
3. **@SpringBootTest** với service thật: transaction boundaries, DTO mapping, business validation, rollback semantics; cần khi integration nhiều bean.
4. **HTTP integration test**: JSON contract, error mapping, no recursive serialization, no LazyInitializationException dưới cấu hình OSIV production.
5. **Database-engine integration**: dùng PostgreSQL/MySQL/... gần production nếu liên quan FK constraints, lock, bulk deletes, generated columns, custom SQL hoặc migration.
6. **Performance test/SQL counting**: đo N+1 và query plan trên fixture đủ lớn; không khẳng định vài H2 rows cho biết latency production.

**Không biến một @DataJpaTest xanh thành kết luận mọi tầng đã đúng.** Nó là bằng chứng cho JPA mapping và repository với database test, không có MVC controller, external service, production security hay transaction isolation tương tự deployment nếu chưa kiểm thử riêng.

## 16. Bài tập phản chứng

**A.** Parent có @OneToMany(mappedBy="order"), child có @ManyToOne @JoinColumn("order_id"). Phía nào quản lý FK? **Child.order**, vì @ManyToOne là owning side. mappedBy chỉ định inverse reference.

**B.** Parent dùng cascade=REMOVE nhưng orphanRemoval=false. Remove một child khỏi List có chắc DELETE row không? **Không**. REMOVE lan khi remove parent, không tự xóa orphan khi chỉ unlink.

**C.** Bật orphanRemoval=true trên collection trỏ shared Product. Có an toàn không? **Không** nếu Product dùng chung, vì tách association có thể xóa một entity còn cần ở nơi khác.

**D.** @ManyToOne không ghi fetch thì mặc định là gì? **EAGER** theo JPA, nên cân nhắc LAZY tường minh cho nhiều use case.

**E.** Trong @DataJpaTest, gọi getLines().size() sau findById thành công. Có chứng minh API REST trả entity sẽ không gặp LazyInitializationException không? **Không**, vì test transaction vẫn còn mở.

**F.** entityManager.clear() trước repository.findById giúp ích gì? Nó loại first-level managed instances để kiểm tra behavior lấy lại từ database, không chỉ Java objects đã có.

**G.** Khi entity đã detach nhưng collection đã initialize trước đó, gọi size() có luôn ném LazyInitializationException không? **Không**; dữ liệu collection đã load vẫn có thể đọc từ memory.

**H.** Vì sao @EntityGraph hữu ích? Nó cho phép một repository method fetch association theo use case mà không biến toàn bộ entity mapping thành EAGER.

**I.** Một query list parents sau đó gọi mỗi parent's lazy children gây N+1. Cách xử lý? Dùng EntityGraph/JOIN FETCH hoặc projection/batch fetch có đo SQL, nhưng chú ý collection pagination.

**J.** Bulk JPQL DELETE order có giống repository.delete(managedOrder) về cascade không? **Không**; bulk bypass entity lifecycle, cần xử lý FK/children riêng.

**K.** Nếu service chỉ cập nhật dirty field trên managed OrderLine, có phải cứ thiếu cascade MERGE là update thất bại? **Không nhất thiết**; dirty checking của managed entity diễn ra trong persistence context. Cascade MERGE chủ yếu liên quan merge operation qua relationship, không phải mọi UPDATE SQL.

**L.** Flush xong test vẫn rollback. Có mâu thuẫn không? **Không**. Flush gửi SQL trong transaction; commit mới kết thúc transaction thành công, còn @DataJpaTest rollback khi test kết thúc.

### Checklist review và QA

- Đã chọn đúng @OneToOne/@OneToMany/@ManyToOne/@ManyToMany theo cardinality?
- Cột FK ở bảng nào và annotation **owning side** nằm trên field nào?
- **mappedBy** trỏ tên Java field đúng hay bị nhầm tên SQL column?
- Helper add/remove cập nhật **cả collection và child reference**?
- Cascade PERSIST/MERGE/REMOVE có khớp **vòng đời sở hữu**, tránh xóa shared entity?
- Có hiểu rõ **cascade REMOVE vs orphanRemoval** trên thao tác remove parent/remove child?
- Orphan removal đã được kiểm tra sau **flush/clear** bằng row existence chưa?
- Quan hệ to-one có fetch LAZY tường minh khi không cần tải mặc định?
- Test LAZY có **clear/reload/isInitialized** để không bị L1 cache che?
- Test detached LAZY có xác nhận collection chưa initialize trước detach?
- Service đọc association trong transaction và map DTO trước khi thoát transaction?
- Có thử **@EntityGraph/JOIN FETCH** theo use case thay vì EAGER toàn cục?
- Có kiểm tra N+1, duplicate parents, pagination với collection fetch và số SQL thực tế khi có yêu cầu hiệu năng?
- Có tránh serialize entity graph hai chiều thẳng ra JSON?
- SQL vendor, FK schema và DB migration quan trọng đã được test trên engine gần production?
- Test có báo đúng giới hạn **@DataJpaTest transaction rollback** và không nhầm flush với commit?

**Kết luận:** **Owning side** quyết định cập nhật FK, **cascade** quyết định truyền operation giữa entities, **orphanRemoval** quyết định xóa child khi rời association sở hữu, và **LAZY** quyết định khi association được tải trong persistence context. Muốn kiểm chứng chúng, hãy dùng **@DataJpaTest + flush/clear/reload + SQL/row assertions**, thay vì chỉ xem một Java List; thêm **@EntityGraph/JOIN FETCH và DTO mapping trong transaction** cho use case cần children, không bật EAGER toàn cục để che LazyInitializationException.

## Tài liệu chính thức

- Hibernate ORM 6.6 User Guide — Associations, cascading, orphan removal, lazy fetching: https://docs.hibernate.org/orm/6.6/userguide/html_single/
- Hibernate ORM 6.6 — Introduction to Hibernate 6, entity graphs and lazy fetching: https://docs.hibernate.org/orm/6.6/introduction/html_single/
- Spring Data JPA — JPA Query Methods và EntityGraph: https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html
- Spring Boot 3.4 — Testing Spring Boot Applications, Auto-configured Data JPA Tests: https://docs.spring.io/spring-boot/3.4/reference/testing/spring-boot-applications.html
- Jakarta Persistence 3.1 Specification — Relationships, cascade, orphanRemoval và fetch: https://jakarta.ee/specifications/persistence/3.1/jakarta-persistence-spec-3.1
