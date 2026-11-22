# Tái hiện khác biệt giữa persist và merge với entity đã tách trong JPA

Trong Java Persistence API (JPA), hai phương thức **EntityManager.persist()** và **EntityManager.merge()** đều liên quan đến việc đưa dữ liệu của đối tượng vào cơ sở dữ liệu. Tuy nhiên, chúng xử lý **đối tượng mới**, **đối tượng đang được quản lý (managed)** và **đối tượng đã tách khỏi persistence context (detached)** theo cách khác nhau. Sự khác biệt này thể hiện rất rõ khi một entity được đọc trong một giao dịch, rời khỏi giao dịch đó, bị chỉnh sửa rồi được đưa trở lại một EntityManager khác.

Bài thực hành sẽ dùng Java, Jakarta Persistence, Hibernate ORM và H2 để quan sát hành vi thực tế. Toàn bộ thí nghiệm chạy trên một cơ sở dữ liệu trong bộ nhớ; không cần Spring hay một máy chủ database riêng. Mục tiêu là phân biệt **entity instance** trong bộ nhớ với **bản ghi** trong database, nắm được bản sao mà merge trả về, và hiểu vì sao cập nhật entity đã tách phải được xử lý thận trọng.

## 1. Bốn trạng thái quan trọng của một entity

Một entity JPA có thể trải qua các trạng thái sau:

| Trạng thái | Ý nghĩa | EntityManager có quản lý không? | Thao tác thường gặp |
| --- | --- | --- | --- |
| **New / transient** | Đối tượng mới tạo bằng Java, chưa gắn với persistence context | Không | Tạo bằng constructor; gọi persist để lưu mới |
| **Managed / persistent** | Đối tượng đang được một persistence context theo dõi | Có | find, persist, merge trả về một managed instance |
| **Detached** | Đã từng được quản lý nhưng hiện nằm ngoài persistence context | Không | Sau close, clear hoặc detach |
| **Removed** | Đã được đánh dấu xóa trong persistence context hiện tại | Có trạng thái xóa | remove; SQL DELETE thường được thực hiện khi flush |

Sơ đồ tối giản:

~~~text
new Student("Lan")
      |
      | persist(s)
      v
   MANAGED --------------------------+
      |                              |
      | close / clear / detach       | transaction commit / flush
      v                              | (đồng bộ với database)
   DETACHED                           |
      |                              |
      | merge(detached)              |
      v                              |
   MANAGED COPY ---------------------+

Lưu ý: merge không đổi chính đối tượng detached thành managed.
~~~

**Persistence context** là tập các entity mà EntityManager đang theo dõi, kèm cơ chế đồng nhất theo khóa định danh và dirty checking. Một database row có thể tương ứng với nhiều Java object ở các EntityManager khác nhau. Một đối tượng đã detached vẫn có ID và dữ liệu của lần tải trước, nhưng thay đổi trên nó **không tự động** được lưu xuống database.

## 2. persist và merge khác nhau như thế nào?

| Tình huống | persist(entity) | merge(entity) |
| --- | --- | --- |
| Entity **new** | Làm **chính instance truyền vào** trở thành managed; dự kiến INSERT | Tạo hoặc lấy managed instance và **sao chép trạng thái** từ instance truyền vào; trả managed instance đó |
| Entity **managed** | Không cần tạo instance khác; thường không có thao tác mới trên chính entity | Trả về managed instance tương ứng; trạng thái vẫn do persistence context quản lý |
| Entity **detached** | Không dùng để gắn lại: có thể phát sinh **EntityExistsException** hoặc lỗi persistence tại thời điểm gọi/flush/commit | Sao chép trạng thái của detached vào managed instance tương ứng và **trả về instance managed** |
| Tham chiếu sau lời gọi | Với entity mới, vẫn dùng cùng object đã được quản lý | Phải dùng **giá trị trả về** để tiếp tục thao tác trong transaction |
| SQL | INSERT khi đồng bộ; có thể xảy ra sớm để lấy ID | Có thể SELECT để nạp entity; UPDATE/INSERT tùy trạng thái và bản ghi, tại flush/commit |

JPA không quy định mọi provider phải ném cùng một lớp exception vào cùng thời điểm đối với **persist(detached)**. Việc có bao nhiêu câu SELECT/INSERT/UPDATE và chúng xuất hiện chính xác lúc nào còn phụ thuộc provider, chiến lược sinh ID, flush mode và cache. Thí nghiệm sẽ kiểm tra **hành vi được bảo đảm**, không dựa vào thứ tự SQL cố định.

## 3. Chuẩn bị dự án chạy độc lập

Yêu cầu: **JDK 17+**, Maven và terminal. Tạo cấu trúc:

~~~text
jpa-detached-lab/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       ├── Student.java
        │       └── DetachedLab.java
        └── resources/
            └── META-INF/
                └── persistence.xml
~~~

### 3.1. pom.xml

Ví dụ dùng Hibernate ORM 6.x với Jakarta Persistence và H2. Các phiên bản được ghim để thí nghiệm có cấu hình lặp lại được; khi áp dụng cho dự án đang có, chọn bộ phiên bản tương thích với nền tảng dự án.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>jpa-detached-lab</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.hibernate.orm</groupId>
            <artifactId>hibernate-core</artifactId>
            <version>6.6.3.Final</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>org.slf4j</groupId>
            <artifactId>slf4j-simple</artifactId>
            <version>2.0.16</version>
            <scope>runtime</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.4.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 3.2. persistence.xml

Đặt file trong **src/main/resources/META-INF/persistence.xml**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<persistence xmlns="https://jakarta.ee/xml/ns/persistence"
             version="3.1">
    <persistence-unit name="detachedLab" transaction-type="RESOURCE_LOCAL">
        <provider>org.hibernate.jpa.HibernatePersistenceProvider</provider>
        <class>demo.Student</class>

        <properties>
            <property name="jakarta.persistence.jdbc.driver" value="org.h2.Driver"/>
            <property name="jakarta.persistence.jdbc.url"
                      value="jdbc:h2:mem:detached_lab;DB_CLOSE_DELAY=-1"/>
            <property name="jakarta.persistence.jdbc.user" value="sa"/>
            <property name="jakarta.persistence.jdbc.password" value=""/>

            <property name="hibernate.hbm2ddl.auto" value="create-drop"/>
            <property name="hibernate.show_sql" value="true"/>
            <property name="hibernate.format_sql" value="true"/>
        </properties>
    </persistence-unit>
</persistence>
~~~

**RESOURCE_LOCAL** cho phép dùng EntityTransaction thủ công, phù hợp một chương trình Java chạy ngoài Spring. **create-drop** tạo/xóa schema cho mục đích thực hành; tuyệt đối không dùng giá trị này trên database sản xuất chứa dữ liệu cần giữ.

### 3.3. Entity dùng cho bài thực hành

**src/main/java/demo/Student.java**:

~~~java
package demo;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "students")
public class Student {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "display_name", nullable = false)
    private String displayName;

    @Version
    private long version;

    protected Student() {
        // Constructor không tham số cho JPA.
    }

    public Student(String displayName) {
        rename(displayName);
    }

    public Long getId() {
        return id;
    }

    public String getDisplayName() {
        return displayName;
    }

    public long getVersion() {
        return version;
    }

    public void rename(String newName) {
        if (newName == null || newName.isBlank()) {
            throw new IllegalArgumentException("Name must not be blank");
        }
        this.displayName = newName;
    }
}
~~~

Trong ví dụ, **id** được database sinh ra; **@Version** dùng optimistic locking để phát hiện cập nhật cạnh tranh. Tránh viết public setter cho ID chỉ nhằm thử merge: việc tự gán ID có thể khiến JPA/Hibernate phân loại sai trạng thái của entity và che khuất chính hiện tượng cần quan sát.

## 4. Chương trình thực nghiệm đầy đủ

Đặt nội dung sau trong **src/main/java/demo/DetachedLab.java**:

~~~java
package demo;

import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.EntityTransaction;
import jakarta.persistence.Persistence;

public class DetachedLab {
    public static void main(String[] args) {
        EntityManagerFactory emf =
                Persistence.createEntityManagerFactory("detachedLab");
        try {
            // Bước 1: persist đối tượng NEW trong EntityManager thứ nhất.
            Student detached = createAndDetach(emf);
            Long id = detached.getId();

            // Bước 2: sửa object sau khi EntityManager đã đóng.
            detached.rename("Lan - edited offline");
            System.out.println("B2. Java detached = " + detached.getDisplayName());
            System.out.println("B2. DB before merge = " + readName(emf, id));

            // Bước 3: cố gắng persist lại entity detached.
            tryPersistDetached(emf, detached);
            System.out.println("B3. DB after persist attempt = " + readName(emf, id));

            // Bước 4: merge, xem identity và tiếp tục sửa trên managed copy.
            mergeAndInspect(emf, detached);
            System.out.println("B4. Java detached = " + detached.getDisplayName());
            System.out.println("B4. DB after merge = " + readName(emf, id));
        } finally {
            emf.close();
        }
    }

    private static Student createAndDetach(EntityManagerFactory emf) {
        EntityManager em = emf.createEntityManager();
        try {
            em.getTransaction().begin();

            Student student = new Student("Lan");
            System.out.println("B1. Managed before persist = " + em.contains(student));
            em.persist(student);
            System.out.println("B1. Managed after persist = " + em.contains(student));

            em.getTransaction().commit();
            System.out.println("B1. New row ID = " + student.getId());
            return student;
        } catch (RuntimeException ex) {
            rollbackIfActive(em);
            throw ex;
        } finally {
            em.close(); // student sẽ detached sau khi close().
        }
    }

    private static String readName(EntityManagerFactory emf, Long id) {
        EntityManager em = emf.createEntityManager();
        try {
            Student found = em.find(Student.class, id);
            return found == null ? "(not found)" : found.getDisplayName();
        } finally {
            em.close();
        }
    }

    private static void tryPersistDetached(EntityManagerFactory emf,
                                           Student detached) {
        EntityManager em = emf.createEntityManager();
        try {
            EntityTransaction tx = em.getTransaction();
            tx.begin();
            System.out.println("B3. Already managed? " + em.contains(detached));

            em.persist(detached);
            em.flush(); // buộc phát hiện lỗi nếu provider trì hoãn.

            // Nếu provider không báo lỗi ở đây, vẫn rollback thí nghiệm.
            System.out.println("B3. Provider accepted persist(detached): inspect behavior");
            tx.rollback();
        } catch (RuntimeException ex) {
            rollbackIfActive(em); // sau lỗi persistence, không commit giao dịch.
            System.out.println("B3. persist(detached) failed: "
                    + ex.getClass().getSimpleName());
        } finally {
            em.close();
        }
    }

    private static void mergeAndInspect(EntityManagerFactory emf,
                                        Student detached) {
        EntityManager em = emf.createEntityManager();
        try {
            em.getTransaction().begin();
            System.out.println("B4. Detached managed before merge = "
                    + em.contains(detached));

            Student managed = em.merge(detached);

            System.out.println("B4. detached == managed = "
                    + (detached == managed));
            System.out.println("B4. detached is managed = "
                    + em.contains(detached));
            System.out.println("B4. returned object is managed = "
                    + em.contains(managed));
            System.out.println("B4. merged name initially = "
                    + managed.getDisplayName());

            // Chỉ sửa detached sau merge: thay đổi này KHÔNG được track.
            detached.rename("Lan - change on detached after merge");
            // Sửa object do merge trả về: thay đổi này được track.
            managed.rename("Lan - saved through managed copy");

            em.getTransaction().commit();
        } catch (RuntimeException ex) {
            rollbackIfActive(em);
            throw ex;
        } finally {
            em.close();
        }
    }

    private static void rollbackIfActive(EntityManager em) {
        EntityTransaction tx = em.getTransaction();
        if (tx.isActive()) {
            tx.rollback();
        }
    }
}
~~~

Các giao dịch được tạo tách biệt để một lần **persist(detached)** thất bại không làm hỏng bước **merge()** tiếp theo. Sau mỗi lần dùng, EntityManager được đóng trong **finally**.

## 5. Chạy thí nghiệm và quan sát

Tại thư mục chứa pom.xml, chạy:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.DetachedLab
~~~

Các dòng liên quan từ chương trình thường có dạng:

~~~text
B1. Managed before persist = false
B1. Managed after persist = true
B1. New row ID = 1
B2. Java detached = Lan - edited offline
B2. DB before merge = Lan
B3. Already managed? false
B3. persist(detached) failed: ...
B3. DB after persist attempt = Lan
B4. Detached managed before merge = false
B4. detached == managed = false
B4. detached is managed = false
B4. returned object is managed = true
B4. merged name initially = Lan - edited offline
B4. Java detached = Lan - change on detached after merge
B4. DB after merge = Lan - saved through managed copy
~~~

Dấu **...** ở dòng lỗi được dùng có chủ ý: thông báo và loại exception có thể thay đổi tùy provider. Log còn xen các câu SQL hoặc thông báo khởi động Hibernate. ID trong ví dụ có thể khác **1** nếu môi trường được cấu hình khác.

### Giải thích từng bước

**Bước 1 — persist một object mới.** Constructor tạo một Student chưa managed. Sau khi gọi **persist(student)**, **em.contains(student)** là true: chính object đó được gắn vào persistence context. Hibernate sử dụng SQL INSERT để tạo bản ghi, có thể thực thi ngay lúc persist vì chiến lược **IDENTITY** cần lấy ID. Commit bảo đảm giao dịch hoàn tất, còn close làm object trở thành detached.

**Bước 2 — sửa entity đã detached.** Gọi **detached.rename(...)** chỉ đổi trạng thái Java của object. Không còn persistence context nào theo dõi thay đổi này, nên truy vấn từ EntityManager mới vẫn thấy tên **Lan**. Có ID không đồng nghĩa với managed.

**Bước 3 — thử persist lại detached.** Đây không phải API để reattach entity. Với Hibernate theo cấu hình này, thao tác thường báo lỗi dạng entity đã detached được đưa vào persist; JPA cho phép lỗi phát sinh lúc gọi hoặc khi flush/commit. Giao dịch lỗi phải rollback. Sau đó đọc lại database để thấy thử nghiệm không lưu tên offline.

**Bước 4 — merge detached.** **em.merge(detached)** tìm hoặc tạo managed instance tương ứng trong persistence context, chép trạng thái đang có trên detached và trả về tham chiếu managed. **detached == managed** là false, **em.contains(detached)** vẫn false, còn **em.contains(managed)** là true. Chỉnh sửa detached lần nữa **sau merge** không tự đồng bộ. Chỉnh sửa managed instance được dirty checking phát hiện; khi commit, database nhận giá trị **Lan - saved through managed copy**.

Điểm cần nhớ: **merge trả một đối tượng khác có trạng thái được quản lý; không biến đối tượng đầu vào thành managed**. Vì vậy code thực tế phải sử dụng object do merge trả về khi cần tiếp tục sửa trong cùng transaction.

## 6. Dự đoán tác động lên SQL

Với thí nghiệm này, Hibernate có thể tạo log SQL tương tự:

~~~sql
-- persist một Student mới (có thể INSERT ngay khi cần ID)
insert into students (display_name, version, id)
values (?, ?, default);

-- EntityManager khác đọc lại bản ghi
select id, display_name, version
from students
where id = ?;

-- merge detached thường cần tìm trạng thái hiện tại của row
select id, display_name, version
from students
where id = ?;

-- update do dirty checking khi flush / commit
update students
set display_name = ?, version = ?
where id = ? and version = ?;
~~~

Các câu SQL trên **mô tả kiểu thao tác**; tên cột, danh sách cột, thứ tự tham số và số lần SELECT thực tế có thể khác với log thật. **@Version** thường thêm điều kiện version vào UPDATE để bảo vệ khỏi cập nhật cạnh tranh. Không dùng nội dung log SQL minh họa làm tiêu chí duy nhất để kết luận thành công.

Một thí nghiệm nhỏ có thể thử ngay: trong **mergeAndInspect()**, bỏ dòng **managed.rename("Lan - saved through managed copy")**, chỉ sửa **detached** sau khi merge. Khi đó database sẽ lưu giá trị **Lan - edited offline** (trạng thái được sao chép *tại thời điểm merge*), chứ không phải **Lan - change on detached after merge**.

## 7. Biến thể: detach trong cùng EntityManager

Đối tượng có thể detached mà **không cần đóng** EntityManager. Ví dụ, trong một transaction đã được mở:

~~~java
Student student = em.find(Student.class, existingId);
System.out.println(em.contains(student)); // true

em.detach(student);
System.out.println(em.contains(student)); // false

student.rename("Offline change");          // chưa được JPA theo dõi
Student managedAgain = em.merge(student);
System.out.println(em.contains(student));    // false
System.out.println(em.contains(managedAgain)); // true
~~~

**em.detach(student)** chỉ tách một entity được chỉ định (cùng ảnh hưởng cascade detach nếu mapping yêu cầu); **em.clear()** xóa mọi managed entity khỏi persistence context; **em.close()** kết thúc persistence context gắn với EntityManager đó. Cần phân biệt **flush** (đồng bộ thao tác SQL) với **commit** (xác nhận giao dịch); flush không làm object detached, và flush xong vẫn có thể rollback.

Một biến thể khác: **em.find(Student.class, id)** trước khi gọi merge. Khi instance managed cho cùng ID đã tồn tại trong persistence context, merge sẽ sao chép state của detached vào **managed instance sẵn có**. EntityManager duy trì một managed entity cho một khóa định danh trong một persistence context.

## 8. Trường hợp hay gây hiểu nhầm

### 8.1. merge không phải lệnh UPDATE trực tiếp

**merge()** là thao tác trên **trạng thái entity**, không phải một câu lệnh SQL cố định. JPA có thể cần SELECT để nạp bản ghi hiện tại, sao chép thuộc tính, theo dõi thay đổi rồi UPDATE khi flush. Khi merge một entity chưa từng được lưu, provider có thể tạo managed copy mới và INSERT. Tuy nhiên, **không nên dùng merge như một UPSERT tổng quát**: với entity có ID/version do provider sinh ra nhưng bản ghi đã bị xóa, các phiên bản provider có thể phát hiện stale state và báo lỗi thay vì insert lại.

### 8.2. Cẩn thận với giá trị cũ trên detached

Giả sử client tải Student khi tên là **Lan**, sau đó người khác đổi thành **Lan Anh**. Một request cũ gửi lại detached state **Lan** có thể ghi đè tên mới nếu không có cơ chế kiểm soát concurrency. **@Version** giúp phát hiện xung đột bằng giá trị version cũ và báo **OptimisticLockException** hoặc exception được bao bọc, tại merge/flush/commit tùy provider.

Không nên tùy tiện vô hiệu hóa version hoặc bỏ qua lỗi stale state để "cho merge luôn thành công". Ứng dụng cần trả thông báo xung đột hoặc yêu cầu người dùng tải lại dữ liệu.

### 8.3. Cascade PERSIST và MERGE khác nhau

Khi có quan hệ Parent–Child, **CascadeType.PERSIST** lan truyền persist sang entity liên kết; **CascadeType.MERGE** lan truyền merge. **CascadeType.ALL** bao gồm cả hai (và các thao tác khác), vì vậy chỉ dùng khi thực sự phù hợp với quyền sở hữu vòng đời của quan hệ. Nếu đưa detached graph lớn vào merge, có thể sao chép nhiều nhánh không mong muốn hoặc gây cập nhật dữ liệu cũ.

Đặc biệt, không tự động merge nguyên Entity được dựng trực tiếp từ JSON của client khi client không có quyền sửa mọi trường hoặc quan hệ.

### 8.4. Có nên gọi save() trong Spring Data JPA?

Trong Spring Data JPA, **JpaRepository.save()** thường chọn **persist** cho entity được xác định là mới, còn entity không mới thường đi qua **merge**. Cách nhận biết "mới" chịu ảnh hưởng bởi metadata ID, **@Version**, **Persistable.isNew()** và cấu hình repository. Vì vậy đừng suy ra rằng save() luôn trả đúng cùng object hoặc rằng ID khác null đồng nghĩa chắc chắn đã có row.

Đối với thao tác cập nhật miền, cách viết tường minh thường dễ kiểm soát hơn:

~~~java
@Transactional
public void renameStudent(Long id, String name) {
    Student managed = repository.findById(id)
        .orElseThrow(() -> new IllegalArgumentException("Student not found"));
    managed.rename(name);
    // Dirty checking ghi thay đổi khi flush/commit.
}
~~~

Trong giao dịch ghi, nếu entity đã managed thì **không bắt buộc** gọi save chỉ để JPA dirty checking hoạt động. Cách nạp entity hiện tại và gọi hành vi miền cũng tránh ghi đè các thuộc tính mà request không được phép chỉnh sửa.

## 9. Bài tập tự mở rộng

1. **Thay đổi detached trước merge và sau merge:** chạy đúng ví dụ, ghi lại hai giá trị database và giải thích vì sao chúng khác nhau.
2. **Bỏ dòng managed.rename:** dự đoán giá trị cuối cùng và giải thích merge đã copy trạng thái ở thời điểm nào.
3. **Dùng em.detach() thay cho close():** thực hiện trong một EntityManager rồi so sánh giá trị em.contains trước và sau detach.
4. **Gọi merge hai lần:** quan sát tham chiếu managed trả về trong cùng persistence context; kiểm tra đồng nhất bằng toán tử **==** và em.contains().
5. **Thử phiên bản cũ:** mở hai EntityManager, mỗi bên đọc Student cùng version; commit thay đổi ở bên thứ nhất rồi thử commit thay đổi bên thứ hai. Ghi nhận lỗi optimistic locking và rollback transaction thất bại.
6. **Đổi GenerationType:** so sánh SQL và thời điểm gán ID khi dùng IDENTITY với SEQUENCE ở database hỗ trợ sequence. Xác nhận rằng thay đổi chiến lược sinh ID **không thay đổi** quy tắc bản chất giữa persist và merge.

Khi đối chiếu kết quả, nên theo dõi đồng thời **instance Java**, **em.contains()**, **ID/version**, **SQL phát sinh** và **giá trị đọc lại bằng EntityManager mới**. Chỉ dựa vào một dòng SQL hoặc một giá trị trong bộ nhớ rất dễ dẫn tới kết luận sai.

## 10. Kết luận thực hành

**persist()** dành cho entity mới và khiến **chính object được truyền vào** trở thành managed. **merge()** hữu ích khi cần sao chép trạng thái của một entity detached vào persistence context, nhưng **object gốc vẫn detached**; chỉ managed instance được trả về tiếp tục được JPA theo dõi. Sửa object detached sau merge không tự động trở thành một lần UPDATE.

Trong ứng dụng thực tế, ưu tiên nạp entity hiện có trong một transaction, kiểm tra nghiệp vụ và thay đổi managed entity; dùng merge có chủ đích khi dữ liệu detached là một phần của thiết kế. Kết hợp **@Version**, kiểm soát các trường cho phép cập nhật và xử lý lỗi giao dịch sẽ giúp tránh mất dữ liệu khi nhiều người cùng thay đổi một bản ghi.
