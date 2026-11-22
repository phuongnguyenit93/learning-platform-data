# Các trạng thái transient, managed, detached và removed

JPA không chỉ ánh xạ một lớp Java thành bảng dữ liệu. Nó còn quản lý vòng đời của từng object entity trong một **persistence context** (ngữ cảnh lưu trữ). Tùy object đang ở trạng thái nào, JPA có thể theo dõi thay đổi, tự ghi dữ liệu, bỏ qua thay đổi hoặc lên lịch xóa object khỏi database.

Bốn trạng thái cốt lõi cần phân biệt:

- **Transient (new)**: object Java mới, chưa được persistence context quản lý và chưa có bản ghi được quản lý tương ứng trong database.
- **Managed**: object đang được một persistence context quản lý; thay đổi có thể được dirty checking phát hiện và đồng bộ.
- **Detached**: object từng được quản lý nhưng hiện không còn thuộc persistence context đó; thay đổi không tự động được đồng bộ.
- **Removed**: entity đang được quản lý nhưng đã được đánh dấu xóa; lệnh DELETE sẽ được thực hiện khi flush.

Hiểu đúng các trạng thái giúp bạn biết lúc nào cần gọi persist, merge hoặc remove, vì sao không cần gọi save sau mọi thay đổi, và vì sao một entity detached không tự cập nhật database.

**Điều kiện của ví dụ:** các đoạn mã dùng Spring Boot 3.x, Java 17 trở lên và Jakarta Persistence. Ứng dụng cần dependency spring-boot-starter-data-jpa, JDBC driver, DataSource và schema phù hợp. Các đoạn mã là những phần của ứng dụng Spring Boot, không phải chương trình độc lập có thể chạy chỉ bằng javac.

## 1. Persistence context là gì?

Persistence context là một tập hợp các entity instance được JPA quản lý trong một đơn vị làm việc. EntityManager là API chính để tương tác với persistence context.

Một persistence context có các trách nhiệm quan trọng:

1. Theo dõi entity managed và các thay đổi của chúng.
2. Duy trì một identity map: trong cùng persistence context, một định danh entity tương ứng với một managed instance duy nhất.
3. Thực hiện dirty checking để phát hiện thay đổi.
4. Lên lịch INSERT, UPDATE và DELETE.
5. Đồng bộ các thay đổi xuống database khi flush.

Ví dụ, trong cùng một persistence context:

~~~java
Book first = entityManager.find(Book.class, 10L);
Book second = entityManager.find(Book.class, 10L);

System.out.println(first == second);
~~~

Với cùng một entity type và ID trong cùng persistence context, kết quả là:

~~~text
true
~~~

Hai lần tìm cùng định danh trả về cùng managed object. Điều này giúp tránh hai bản managed khác nhau cùng đại diện cho một hàng trong cùng persistence context.

Persistence context thường được Spring quản lý gắn với transaction. Khi transaction kết thúc và context đóng, các entity không còn được quản lý bởi context đó; chúng trở thành detached đối với context đã đóng.

## 2. Bốn trạng thái của entity

| Trạng thái | Có thuộc persistence context? | Tự động dirty checking? | Có thể ghi dữ liệu? |
|---|---|---|---|
| Transient | Không | Không | Chưa, cần persist hoặc merge phù hợp |
| Managed | Có | Có | Có, khi flush/commit |
| Detached | Không | Không | Không tự động; cần merge hoặc thao tác khác |
| Removed | Đang được context quản lý theo trạng thái removed | Không còn được xem như entity bình thường để cập nhật | Được lên lịch DELETE khi flush |

Có thể hình dung các chuyển trạng thái chính:

~~~text
                    persist()
     TRANSIENT ----------------------> MANAGED
         |                                |
         | merge()                        | remove()
         v                                v
  MANAGED COPY                         REMOVED
         ^                                |
         |                                | flush / commit
         | merge()                        v
     DETACHED <---------------------- (deleted in DB)
         ^
         |
   detach() / clear() / close()
         |
     MANAGED

MANAGED -- transaction-scoped context closes --> DETACHED
MANAGED -- refresh() --> MANAGED (state reloaded from DB)
~~~

Sơ đồ nhấn mạnh các đường chuyển phổ biến. Merge tạo hoặc cập nhật một managed instance đích; nó không biến chính object detached nguồn thành managed. Removed là trạng thái được đánh dấu xóa và thao tác xóa được đồng bộ khi flush.

## 3. Transient: object mới chưa được JPA quản lý

Transient (còn gọi là new) là object Java được tạo bằng toán tử new nhưng chưa được đưa vào persistence context.

Ví dụ:

~~~java
Book book = new Book("Spring Data JPA");
~~~

Tại thời điểm này:

- Object tồn tại trong bộ nhớ JVM.
- JPA chưa theo dõi object.
- Thay đổi field chỉ thay đổi object trong bộ nhớ.
- Không có INSERT nào được lên lịch chỉ vì object được tạo.
- Nếu không persist hoặc merge, object không tự được lưu vào database.

Ví dụ:

~~~java
Book book = new Book("Spring Data JPA");
book.changeTitle("Spring Data JPA in Practice");
~~~

Hai dòng trên chỉ thao tác trên object Java. Database không biết về object này.

### Đưa transient entity vào persistence context

Dùng EntityManager:

~~~java
entityManager.persist(book);
~~~

Hoặc dùng Spring Data JPA:

~~~java
bookRepository.save(book);
~~~

Khi Spring Data xác định entity là mới, save thường gọi EntityManager.persist. Entity chuyển sang managed trong persistence context hiện tại.

Lưu ý, thời điểm phát SQL INSERT phụ thuộc chiến lược sinh ID và provider. Với IDENTITY, Hibernate có thể cần insert sớm để lấy khóa; với các chiến lược khác, INSERT thường có thể được trì hoãn tới flush.

## 4. Managed: entity đang được persistence context theo dõi

Managed là trạng thái quan trọng nhất khi làm việc với JPA. Một entity có thể trở thành managed khi:

- Gọi persist trên entity transient.
- Tìm entity bằng EntityManager.find.
- Lấy entity bằng repository query trong persistence context đang hoạt động.
- Gọi merge và sử dụng instance managed được trả về.
- Nhận entity từ quan hệ đã được khởi tạo trong persistence context.

Ví dụ:

~~~java
Book book = entityManager.find(Book.class, 10L);
~~~

Nếu tìm thấy bản ghi, entity trả về là managed trong persistence context hiện tại.

### Dirty checking

JPA theo dõi trạng thái của entity managed. Khi field thay đổi, provider có thể phát hiện thay đổi và tạo UPDATE khi flush.

~~~java
@Transactional
public void renameBook(Long id, String newTitle) {
    Book book = entityManager.find(Book.class, id);
    if (book == null) {
        throw new IllegalArgumentException("Book not found: " + id);
    }

    book.changeTitle(newTitle);
    // Không cần gọi entityManager.merge(book) hay repository.save(book).
}
~~~

Khi transaction hoàn tất, Spring/JPA flush persistence context. Hibernate phát UPDATE nếu phát hiện dữ liệu thay đổi.

Đây là dirty checking. Nó là lý do bạn không cần gọi save sau mỗi setter trên entity managed.

### Identity map và thay đổi nhất quán

Trong cùng persistence context, nếu hai service/repository thao tác trên cùng entity ID, JPA thường dùng cùng một managed instance. Khi một phần code thay đổi instance đó, phần code khác trong cùng context nhìn thấy thay đổi trong bộ nhớ.

Điều này không có nghĩa các transaction khác lập tức thấy thay đổi chưa commit. Transaction isolation và database quyết định khi nào transaction khác nhìn thấy dữ liệu đã commit.

## 5. Detached: entity không còn được quản lý

Detached là object từng được quản lý nhưng đã tách khỏi persistence context. Các nguyên nhân phổ biến:

- Gọi EntityManager.detach(entity).
- Gọi EntityManager.clear() để detach toàn bộ entity managed.
- EntityManager hoặc persistence context đóng.
- Transaction-scoped persistence context kết thúc.

Ví dụ:

~~~java
Book book = entityManager.find(Book.class, 10L);
entityManager.detach(book);

book.changeTitle("New title");
~~~

Sau detach:

- Object vẫn tồn tại trong JVM.
- ID và các field hiện có vẫn còn.
- JPA không còn dirty checking object đó.
- Thay đổi sau detach không tự động được ghi xuống database.
- Lazy association chưa được khởi tạo có thể không truy cập được nếu không còn persistence context phù hợp.

Nếu cần đồng bộ trạng thái detached, có thể dùng merge. Nhưng cần hiểu chính xác semantics của merge.

## 6. merge(): sao chép trạng thái sang managed instance

Một nhầm lẫn phổ biến là cho rằng merge sẽ “gắn lại” chính object detached vào persistence context. Thực tế, JPA sao chép trạng thái của object nguồn vào một managed instance đích rồi trả về instance đích đó.

~~~java
Book detachedBook = ...;

Book managedBook = entityManager.merge(detachedBook);

managedBook.changeTitle("Updated title");
~~~

Sau lời gọi:

- **detachedBook** vẫn detached.
- **managedBook** là instance managed trong persistence context hiện tại.
- Thay đổi tiếp theo nên thực hiện trên managedBook.
- Khi flush, thay đổi của managedBook có thể được ghi xuống database.

Nếu bỏ qua giá trị trả về:

~~~java
entityManager.merge(detachedBook);
detachedBook.changeTitle("Another title");
~~~

thì thay đổi cuối trên detachedBook không được dirty checking theo dõi. Đây là lỗi thường gặp.

### Merge entity transient

Merge cũng có thể nhận object transient. JPA tạo một managed copy và sao chép trạng thái từ object transient sang copy đó. Khi flush, managed copy có thể được insert.

Tuy nhiên, nếu mục tiêu là lưu một entity mới, persist diễn đạt ý định rõ hơn. Với Spring Data JPA, save tự xác định entity mới hay cũ theo cơ chế new-state detection rồi chọn persist hoặc merge.

### Merge graph và cascade MERGE

Nếu entity nguồn có association và mapping khai báo CascadeType.MERGE, trạng thái của entity liên quan cũng được merge theo. Không có cascade MERGE thì không nên giả định toàn bộ graph được merge đệ quy.

Đặc biệt cẩn thận khi merge object detached được dựng từ request DTO không đầy đủ. Field null hoặc association thiếu có thể ghi đè dữ liệu hiện tại trong managed copy. Một quy trình cập nhật an toàn thường tải entity managed trong transaction, kiểm tra quyền và quy tắc nghiệp vụ, rồi chỉ thay đổi các field được phép.

## 7. remove(): đánh dấu entity để xóa

EntityManager.remove yêu cầu entity managed. Khi gọi:

~~~java
Book book = entityManager.find(Book.class, id);
entityManager.remove(book);
~~~

entity chuyển sang trạng thái removed. JPA lên lịch DELETE; SQL thường được thực thi khi flush hoặc commit.

Trạng thái removed không có nghĩa hàng đã biến mất ngay tại thời điểm gọi remove. Trước flush, thao tác có thể mới được ghi nhận trong persistence context.

Các điểm cần nhớ:

- Gọi remove trên entity managed là đường sử dụng thông thường.
- Gọi remove trên entity detached không hợp lệ; cần tải entity managed hoặc xử lý bằng cách phù hợp.
- CascadeType.REMOVE có thể lan truyền remove sang association được cấu hình.
- orphanRemoval có thể lên lịch xóa child khi child bị loại khỏi quan hệ sở hữu phù hợp.

Ví dụ Spring Data:

~~~java
@Transactional
public void deleteBook(Long id) {
    Book book = entityManager.find(Book.class, id);
    if (book == null) {
        return;
    }

    entityManager.remove(book);
}
~~~

Có thể dùng repository.deleteById(id), nhưng semantics thực tế phụ thuộc implementation và trạng thái entity. Khi cần hiểu chính xác lifecycle, hãy xem hành vi của Spring Data JPA version đang dùng và kiểm tra SQL trong integration test.

## 8. detach(), clear() và close()

Ba thao tác này đều ảnh hưởng đến việc entity còn được persistence context quản lý hay không.

### detach(entity)

Tách một entity cụ thể khỏi persistence context:

~~~java
entityManager.detach(book);
~~~

Nếu association có CascadeType.DETACH, thao tác detach có thể lan truyền sang các entity liên quan theo mapping.

### clear()

Tách tất cả entity managed khỏi persistence context:

~~~java
entityManager.clear();
~~~

Clear hữu ích trong batch processing hoặc test khi cần chắc chắn lần đọc sau lấy dữ liệu từ database thay vì dùng managed instance còn trong first-level cache.

Không gọi clear tùy tiện giữa nghiệp vụ nếu còn thay đổi chưa flush; các thay đổi đó sẽ không còn được persistence context theo dõi.

### close()

Khi EntityManager đóng, persistence context của nó kết thúc. Những entity từng được quản lý trở thành detached đối với context đó.

Trong ứng dụng Spring, EntityManager thường được quản lý bởi container/proxy; không tự ý gọi close trên EntityManager được inject vào bean.

## 9. refresh(): nạp lại trạng thái từ database

Refresh áp dụng cho entity managed:

~~~java
entityManager.refresh(book);
~~~

JPA đọc lại trạng thái từ database và đồng bộ object managed với dữ liệu hiện hành theo transaction/database visibility. Các thay đổi chưa flush trên entity có thể bị ghi đè.

Refresh khác merge:

| Thao tác | Hướng dữ liệu | Mục đích |
|---|---|---|
| merge(detached) | Từ object nguồn vào managed copy | Đồng bộ trạng thái object detached/transient vào persistence context |
| refresh(managed) | Từ database vào object managed | Nạp lại trạng thái từ database |

Không dùng refresh như một cách lưu dữ liệu. Nếu muốn ghi thay đổi, hãy để dirty checking/flush thực hiện; refresh có thể loại bỏ chính thay đổi bạn muốn lưu.

## 10. flush() không phải là commit

Flush đồng bộ các thay đổi đang chờ trong persistence context xuống database bằng SQL. Nó không tự kết thúc transaction.

~~~java
entityManager.persist(book);
entityManager.flush();
~~~

Sau flush, câu INSERT có thể đã được gửi tới database, nhưng transaction vẫn có thể rollback. Chỉ commit transaction mới xác nhận các thay đổi theo transaction semantics của database.

Một số thời điểm flush:

- Khi ứng dụng gọi EntityManager.flush hoặc repository.flush.
- Trước commit transaction.
- Trước một truy vấn trong chế độ flush phù hợp, chẳng hạn AUTO, nếu thay đổi đang chờ có thể ảnh hưởng kết quả truy vấn.

Không nên coi flush là bảo đảm dữ liệu đã bền vững với các transaction khác. Nó chỉ đồng bộ trạng thái persistence context xuống database trong transaction hiện tại.

## 11. Vòng đời và thao tác Spring Data JPA save()

Spring Data JPA cung cấp save(entity). Phương thức này không luôn gọi persist và cũng không luôn gọi merge. Repository xác định entity có mới hay không rồi chọn thao tác phù hợp.

Thông thường:

- Entity mới: gọi persist.
- Entity đã tồn tại/detached: gọi merge.

Cách xác định new-state có thể dựa trên trường **@Version** hoặc ID, hoặc cơ chế **Persistable.isNew()** nếu entity triển khai interface này.

Ví dụ:

~~~java
@Transactional
public Long createBook(String title) {
    Book book = new Book(title);

    Book saved = bookRepository.save(book);
    return saved.getId();
}
~~~

Với entity mới, saved thường chính là instance được persist. Nhưng nếu save dùng merge, instance trả về là managed copy; nên tiếp tục dùng object trả về khi cần.

Đối với entity managed đã được tải trong transaction, thường không cần gọi save lại sau khi thay đổi:

~~~java
@Transactional
public void rename(Long id, String title) {
    Book book = bookRepository.findById(id).orElseThrow();
    book.changeTitle(title);
    // Dirty checking sẽ đồng bộ khi flush.
}
~~~

## 12. Rollback và trạng thái object trong bộ nhớ

Khi transaction rollback, database hoàn tác thay đổi của transaction đó. Tuy nhiên, đừng giả định object Java tự quay lại đúng trạng thái trước transaction.

Ví dụ, code đã đổi title của entity managed rồi transaction rollback. Object trong bộ nhớ có thể vẫn giữ title mới dù database đã rollback. Persistence context sau rollback cũng có thể không còn phù hợp để tiếp tục sử dụng như trạng thái nhất quán.

Thực hành an toàn:

- Kết thúc transaction thất bại.
- Không tiếp tục dùng entity từ persistence context đã rollback cho một nghiệp vụ mới.
- Tải lại entity trong transaction mới.
- Nếu cần dữ liệu sau rollback, đọc lại từ database thay vì tin vào object cũ.

Điều này đặc biệt quan trọng khi entity đã được truyền qua nhiều lớp hoặc được giữ trong biến ngoài transaction.

## 13. Ví dụ kiểm tra các trạng thái bằng EntityManager

Bảng sau tóm tắt một luồng lifecycle đơn giản:

| Bước | Thao tác | Trạng thái |
|---|---|---|
| 1 | new Book(...) | Transient |
| 2 | persist(book) | Managed |
| 3 | book.changeTitle(...) | Managed, có thay đổi được theo dõi |
| 4 | flush() | Managed, thay đổi đã đồng bộ SQL trong transaction |
| 5 | detach(book) | Detached |
| 6 | book.changeTitle(...) | Detached, thay đổi không tự đồng bộ |
| 7 | merge(book) | Trả về một managed copy |
| 8 | remove(managedCopy) | Removed |
| 9 | flush()/commit | DELETE được thực thi/transaction được xác nhận |

Một ví dụ minh họa trong test:

~~~java
@DataJpaTest
class BookLifecycleTest {

    @Autowired
    private TestEntityManager testEntityManager;

    @Autowired
    private BookRepository bookRepository;

    @Test
    void entityMovesThroughManagedAndDetachedStates() {
        Book book = new Book("Original");

        testEntityManager.persist(book);
        testEntityManager.flush();

        Long id = book.getId();
        assertThat(testEntityManager.getEntityManager().contains(book)).isTrue();

        testEntityManager.detach(book);
        assertThat(testEntityManager.getEntityManager().contains(book)).isFalse();

        Book managedCopy = testEntityManager.getEntityManager().merge(book);
        assertThat(testEntityManager.getEntityManager().contains(managedCopy)).isTrue();

        assertThat(bookRepository.findById(id)).isPresent();
    }
}
~~~

Test cần entity Book có constructor phù hợp và cấu hình database/schema cho test. **contains(entity)** cho biết entity có thuộc persistence context hiện tại hay không; đây là cách kiểm tra trực tiếp trạng thái managed trong test.

## 14. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Sửa object nhưng database không đổi | Entity đang transient hoặc detached | Persist entity mới hoặc merge và dùng managed copy |
| Gọi merge nhưng object nguồn vẫn detached | Hiểu nhầm merge là reattach | Dùng object managed được merge trả về |
| Không thấy INSERT ngay sau persist | SQL được trì hoãn tới flush hoặc commit | Hiểu lifecycle và flush timing; kiểm tra ID generation |
| Xóa entity detached gây lỗi | remove yêu cầu entity managed | Tải entity trong transaction rồi remove |
| Thay đổi mất sau clear | Clear detach mọi entity và bỏ theo dõi thay đổi chưa flush | Flush trước clear nếu cần giữ thay đổi |
| Dữ liệu object không khớp database sau rollback | Object trong bộ nhớ không tự hoàn nguyên | Kết thúc context thất bại và tải lại entity |
| Hai lần find trả về hai object khác nhau | Đang ở hai persistence context khác nhau hoặc khác identity | So sánh trong cùng context bằng contains/identity |
| Lazy association lỗi sau khi context đóng | Entity detached và association chưa khởi tạo | Tải fetch plan cần thiết trong transaction rồi map DTO |

## 15. Checklist khi làm việc với entity lifecycle

- [ ] Xác định entity đang transient, managed, detached hay removed.
- [ ] Dùng persist cho entity mới khi làm việc trực tiếp với EntityManager.
- [ ] Dùng merge cho trạng thái detached khi thực sự cần đồng bộ graph.
- [ ] Luôn sử dụng instance managed được merge trả về.
- [ ] Dùng remove trên entity managed.
- [ ] Dùng detach/clear có chủ đích và hiểu tác động lên thay đổi chưa flush.
- [ ] Dùng refresh khi muốn loại bỏ thay đổi trong bộ nhớ và nạp lại dữ liệu từ database.
- [ ] Phân biệt flush với commit.
- [ ] Không dựa vào object sau rollback như thể nó đã tự phục hồi.
- [ ] Với Spring Data save(), hiểu cơ chế new-state detection và dùng object trả về.

## 16. Kết luận

Bốn trạng thái transient, managed, detached và removed mô tả mối quan hệ giữa object Java và persistence context. Persist đưa entity mới vào quản lý; find trả về entity managed; merge sao chép trạng thái vào một managed instance; remove đánh dấu entity để xóa; detach/clear kết thúc việc theo dõi; refresh nạp lại trạng thái từ database.

Khi hiểu lifecycle, bạn sẽ biết lúc nào JPA tự dirty checking, lúc nào cần merge, vì sao flush chưa phải commit và vì sao object trong bộ nhớ có thể khác database sau rollback. Đây là nền tảng để viết service và repository an toàn với transaction.