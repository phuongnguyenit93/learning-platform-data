# Thực hiện vòng lưu–đọc–sửa–xóa

## Mục tiêu bài thực hành

Một repository chỉ thực sự hữu ích khi bạn quan sát được đối tượng đi qua đủ vòng đời: được lưu, được đọc lại, được cập nhật và được xóa khỏi kho dữ liệu. Bài thực hành này thuộc chương **Khởi tạo thực hành** của module SPRING_DATA_COMMONS, sử dụng các method của `CrudRepository` để thực hiện vòng đó.

Spring Data Commons cung cấp hợp đồng CRUD dùng chung. Để chạy ví dụ, bài học chọn **Spring Data JPA và H2 trong bộ nhớ** làm công nghệ thực thi. Các annotation JPA, cách sinh ID và transaction trong ví dụ thuộc cách tích hợp cụ thể này; chúng không phải quy tắc chung cho mọi kho dữ liệu Spring Data.

Sau bài học, bạn có thể:

- Khai báo repository với đúng kiểu domain và kiểu định danh.
- Sử dụng `save`, `findById` và `deleteById` theo một chuỗi thao tác có kiểm chứng.
- Phân biệt đối tượng Java đang có trong bộ nhớ với dữ liệu đã được đọc lại từ kho lưu trữ.
- Giải thích vì sao cần dùng kết quả trả về của `save`.
- Nhận diện những chỗ phụ thuộc JPA khi áp dụng cùng hợp đồng CRUD sang kho dữ liệu khác.

## 1. Kết quả cần đạt

Ta quản lý một nhiệm vụ học tập có ba thuộc tính nghiệp vụ và định danh:

| Thuộc tính | Kiểu trong ví dụ | Ý nghĩa |
| --- | --- | --- |
| `id` | `Long` | Định danh được sinh khi lưu đối tượng mới. |
| `title` | `String` | Nội dung nhiệm vụ học tập. |
| `completed` | `boolean` | Nhiệm vụ đã hoàn thành hay chưa. |

Vòng thực hành dùng đúng một đối tượng:

~~~text
Tạo đối tượng mới
    -> lưu, nhận ID
    -> đọc bằng ID
    -> sửa tiêu đề và trạng thái
    -> lưu thay đổi
    -> đọc lại để đối chiếu
    -> xóa bằng ID
    -> đọc lại, xác nhận không còn dữ liệu
~~~

Một lần chạy thành công phải chứng minh được:

1. Đối tượng mới nhận được ID sau khi lưu.
2. Đọc bằng ID trả về đúng dữ liệu đã lưu.
3. Đọc sau cập nhật phản ánh dữ liệu mới và giữ nguyên ID.
4. Đọc sau xóa trả về `Optional.empty()`.

Không dùng việc in lại một biến Java vừa sửa làm bằng chứng cho bước cập nhật. Bằng chứng cần đến từ lời gọi đọc tiếp theo.

## 2. Chuẩn bị một ứng dụng thực hành độc lập

### 2.1. Các thành phần cần có

Chuẩn bị một dự án Spring Boot với bộ phiên bản Spring Boot, Spring Data và Java tương thích, có các dependency:

- Spring Data JPA.
- H2 Database.

Ví dụ bên dưới dùng namespace `jakarta.persistence`. Dự án phải sử dụng bộ JPA tương ứng; không trộn các import `jakarta.persistence` với một cấu hình JPA cũ dùng `javax.persistence`.

Nếu dự án Maven đã có parent hoặc BOM quản lý dependency phù hợp, phần dependency cần thiết có dạng:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jpa</artifactId>
    </dependency>

    <dependency>
        <groupId>com.h2database</groupId>
        <artifactId>h2</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

Đoạn trên là phần dependency của dự án, không phải toàn bộ POM. Nếu chạy bằng Maven, dự án cũng cần cấu hình plugin Spring Boot phù hợp. Để bộ dependency đang quản lý cung cấp version, không tự thêm một version Commons riêng chỉ để thực hiện bài CRUD.

Không cần starter Web cho bài này. Ta dùng `ApplicationRunner` để chạy một vòng thực hành ngay sau khi ứng dụng khởi tạo.

### 2.2. Cấu trúc mã nguồn

~~~text
src/main/java/com/example/commonspractice/
    CommonsPracticeApplication.java
    domain/
        StudyTask.java
    repository/
        StudyTaskRepository.java

src/main/resources/
    application.yml
~~~

Lớp ứng dụng nằm ở package cha `com.example.commonspractice`. Với cấu hình Boot thông thường, các package con chứa entity và repository sẽ nằm trong phạm vi phát hiện mặc định.

Các đường dẫn ở phần này là cấu trúc của dự án thực hành mà người học tạo. Mỗi lớp `public` bên dưới được đặt trong file Java cùng tên.

### 2.3. Cấu hình H2 trong bộ nhớ

Nội dung `application.yml`:

~~~yaml
spring:
  main:
    web-application-type: none

  datasource:
    url: jdbc:h2:mem:commons_practice;DB_CLOSE_DELAY=-1
    username: sa
    password: ""

  jpa:
    hibernate:
      ddl-auto: create-drop
    show-sql: true
    properties:
      hibernate:
        format_sql: true
~~~

Cấu hình này tạo cơ sở dữ liệu H2 trong bộ nhớ để phục vụ bài thực hành:

- `web-application-type: none` làm ứng dụng chạy theo kiểu console.
- `ddl-auto: create-drop` cho Hibernate tạo schema lúc khởi tạo và dọn schema khi đóng context.
- `show-sql` và `format_sql` giúp quan sát câu lệnh SQL.
- `DB_CLOSE_DELAY=-1` giữ cơ sở dữ liệu trong bộ nhớ khi kết nối cuối đóng, cho đến khi JVM kết thúc, trừ khi có thao tác đóng hoặc dọn dữ liệu khác.

Vì ví dụ chủ động tạo rồi dọn schema, hãy sử dụng cấu hình này với cơ sở dữ liệu thực hành độc lập. Dữ liệu ở đây không được thiết kế để tồn tại qua các lần chạy JVM.

## 3. Khai báo đối tượng domain

File `domain/StudyTask.java`:

~~~java
package com.example.commonspractice.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "study_task")
public class StudyTask {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String title;

    @Column(nullable = false)
    private boolean completed;

    protected StudyTask() {
    }

    public StudyTask(String title) {
        rename(title);
        this.completed = false;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public boolean isCompleted() {
        return completed;
    }

    public void rename(String newTitle) {
        if (newTitle == null || newTitle.isBlank()) {
            throw new IllegalArgumentException(
                "Tiêu đề nhiệm vụ không được để trống"
            );
        }
        this.title = newTitle;
    }

    public void markCompleted() {
        this.completed = true;
    }
}
~~~

Những điểm cần hiểu:

- `@Entity` và `@Table` mô tả mapping JPA.
- `@Id` xác định thuộc tính định danh; `@GeneratedValue` chọn cơ chế sinh ID trong ví dụ JPA/H2.
- Constructor không tham số được để `protected` phục vụ JPA.
- Đối tượng mới có ID bằng `null`; mã nghiệp vụ không tự gán ID.
- `rename` và `markCompleted` biểu diễn hành vi thay đổi đối tượng.
- Không có setter cho ID, giúp tránh vô tình đổi định danh khi cập nhật.

`@Column(nullable = false)` và kiểm tra trong `rename` có vai trò khác nhau. Kiểm tra Java chặn tiêu đề rỗng hoặc chỉ có khoảng trắng khi đi qua method này; ràng buộc cột không-null không tự kiểm tra toàn bộ quy tắc đó.

Trong ví dụ, annotation được đặt trên field, nên JPA dùng cách truy cập field. Không cần thêm setter chỉ để JPA có thể ánh xạ những thuộc tính này.

## 4. Khai báo repository bằng hợp đồng Commons

File `repository/StudyTaskRepository.java`:

~~~java
package com.example.commonspractice.repository;

import com.example.commonspractice.domain.StudyTask;
import org.springframework.data.repository.CrudRepository;

public interface StudyTaskRepository
        extends CrudRepository<StudyTask, Long> {
}
~~~

`CrudRepository` được cung cấp bởi Spring Data Commons. Hai tham số kiểu có ý nghĩa:

- `StudyTask` là kiểu đối tượng được quản lý.
- `Long` là kiểu ID, phải khớp với thuộc tính `id` của entity.

Repository không cần tự viết implementation cho những method CRUD kế thừa. Với dependency và cấu hình JPA của ứng dụng, module Spring Data JPA cung cấp cơ chế tạo repository và thực thi các thao tác trên kho dữ liệu.

Bài này chỉ dùng hợp đồng chung, vì vậy không cần chuyển sang `JpaRepository` để có thêm method như `flush`. Trong một ứng dụng JPA khác, `JpaRepository` vẫn có thể là lựa chọn phù hợp nếu cần các khả năng chuyên biệt của JPA.

Các method liên quan:

| Method | Mục đích trong vòng thực hành |
| --- | --- |
| `save(entity)` | Lưu một đối tượng mới hoặc lưu trạng thái cập nhật theo cơ chế của module. |
| `findById(id)` | Tìm một đối tượng, biểu diễn kết quả có hoặc không bằng `Optional`. |
| `deleteById(id)` | Yêu cầu xóa đối tượng theo ID. |

Chỉ khai báo interface chung chưa đủ để truy cập mọi loại cơ sở dữ liệu. JPA starter, entity mapping, datasource và phạm vi đăng ký repository là các phần làm cho hợp đồng đó hoạt động trong ứng dụng này.

## 5. Chạy trọn vòng bằng ApplicationRunner

File `CommonsPracticeApplication.java`:

~~~java
package com.example.commonspractice;

import com.example.commonspractice.domain.StudyTask;
import com.example.commonspractice.repository.StudyTaskRepository;
import java.util.Objects;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class CommonsPracticeApplication {

    public static void main(String[] args) {
        SpringApplication.run(
            CommonsPracticeApplication.class,
            args
        ).close();
    }

    @Bean
    ApplicationRunner crudCycle(StudyTaskRepository repository) {
        return args -> {
            String originalTitle = "Ôn tập Repository";
            String updatedTitle = "Đã thực hành CRUD với Repository";

            // 1. Lưu một đối tượng mới.
            StudyTask draft = new StudyTask(originalTitle);
            require(
                draft.getId() == null,
                "Đối tượng mới chưa được có ID do ứng dụng tự gán"
            );

            StudyTask saved = repository.save(draft);
            Long id = Objects.requireNonNull(
                saved.getId(),
                "Phải nhận được ID sau khi lưu"
            );
            printState("[1] LƯU", saved);

            // 2. Đọc lại đối tượng theo ID vừa nhận.
            StudyTask loaded = repository.findById(id)
                .orElseThrow(() -> new IllegalStateException(
                    "Không tìm thấy nhiệm vụ sau khi lưu: " + id
                ));

            require(
                originalTitle.equals(loaded.getTitle()),
                "Tiêu đề đọc lại phải khớp với dữ liệu đã lưu"
            );
            require(
                !loaded.isCompleted(),
                "Nhiệm vụ mới phải chưa hoàn thành"
            );
            printState("[2] ĐỌC", loaded);

            // 3. Sửa đối tượng đã đọc rồi lưu thay đổi.
            loaded.rename(updatedTitle);
            loaded.markCompleted();

            StudyTask updated = repository.save(loaded);
            require(
                id.equals(updated.getId()),
                "Cập nhật không được làm đổi ID"
            );
            printState("[3] SỬA", updated);

            // 4. Đọc lại để kiểm chứng dữ liệu sau cập nhật.
            StudyTask reloaded = repository.findById(id)
                .orElseThrow(() -> new IllegalStateException(
                    "Không tìm thấy nhiệm vụ sau cập nhật: " + id
                ));

            require(
                updatedTitle.equals(reloaded.getTitle()),
                "Dữ liệu đọc lại phải có tiêu đề mới"
            );
            require(
                reloaded.isCompleted(),
                "Dữ liệu đọc lại phải có trạng thái hoàn thành"
            );
            printState("[4] ĐỌC LẠI", reloaded);

            // 5. Xóa đúng đối tượng do vòng này tạo ra.
            repository.deleteById(id);

            boolean presentAfterDelete =
                repository.findById(id).isPresent();

            require(
                !presentAfterDelete,
                "Không được tìm thấy nhiệm vụ sau khi xóa"
            );

            System.out.printf(
                "[5] XÓA: id=%d, present=%s%n",
                id,
                presentAfterDelete
            );
            System.out.println("CRUD_CYCLE=PASS");
        };
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new IllegalStateException(message);
        }
    }

    private static void printState(String step, StudyTask task) {
        System.out.printf(
            "%s: id=%d, title=%s, completed=%s%n",
            step,
            task.getId(),
            task.getTitle(),
            task.isCompleted()
        );
    }
}
~~~

`ApplicationRunner` được Spring Boot gọi sau khi context khởi tạo. Dependency `StudyTaskRepository` được inject vào bean, nên runner có thể thực hiện vòng dữ liệu ngay khi ứng dụng đã sẵn sàng.

Trong ứng dụng console này, `SpringApplication.run(...)` thực hiện runner trước khi trả về. Sau đó `close()` đóng context để kết thúc ví dụ và dọn các tài nguyên liên quan.

Method `require` ném exception nếu kết quả không đúng, thay vì dùng từ khóa `assert` của Java vốn có thể chưa được bật trong một lần chạy thông thường. Dòng `CRUD_CYCLE=PASS` chỉ xuất hiện sau khi tất cả bước kiểm chứng đều đạt.

## 6. Chạy và đọc kết quả

Nếu dự án có Maven wrapper và plugin Spring Boot phù hợp, có thể chạy từ thư mục gốc của dự án thực hành:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Hoặc chạy method `main` bằng IDE với đúng JDK và classpath của dự án.

Một phần kết quả mong đợi có dạng:

~~~text
[1] LƯU: id=1, title=Ôn tập Repository, completed=false
[2] ĐỌC: id=1, title=Ôn tập Repository, completed=false
[3] SỬA: id=1, title=Đã thực hành CRUD với Repository, completed=true
[4] ĐỌC LẠI: id=1, title=Đã thực hành CRUD với Repository, completed=true
[5] XÓA: id=1, present=false
CRUD_CYCLE=PASS
~~~

ID bằng 1 chỉ là giá trị minh họa. Không viết điều kiện kiểm chứng phụ thuộc vào ID phải là 1 hoặc liên tục, vì việc sinh ID phụ thuộc cấu hình và trạng thái kho dữ liệu.

Log SQL có thể xuất hiện xen kẽ với log ứng dụng. Đừng dùng số lượng hoặc hình thức SQL chính xác làm tiêu chí duy nhất: provider có thể thực hiện thêm câu lệnh để tải entity, kiểm tra trạng thái hoặc xử lý xóa.

Tiêu chí của bài là dữ liệu quan sát được qua repository có đúng ở từng mốc hay không.

## 7. Phân tích từng bước

### 7.1. Lưu: luôn lấy kết quả trả về của save

~~~java
StudyTask saved = repository.save(draft);
Long id = saved.getId();
~~~

`save` trả về đối tượng đã lưu theo hợp đồng repository. Bên gọi nên tiếp tục làm việc với giá trị trả về, nhất là khi cần ID, version hoặc những giá trị được cập nhật trong quá trình lưu.

Không giả định:

~~~java
saved == draft
~~~

luôn đúng cho mọi trường hợp và mọi module.

Với JPA, đối tượng mới và đối tượng đã có định danh có thể đi qua các cơ chế khác nhau như persist và merge. Đối tượng trả về của quá trình merge có thể khác instance đầu vào. Commons không yêu cầu mọi kho dữ liệu triển khai các cơ chế đó giống nhau.

ID không-null giúp ta có khóa để đọc lại, nhưng tự nó chưa phải bằng chứng tổng quát rằng dữ liệu đã commit trong mọi thiết kế transaction. Bài này kiểm chứng thêm bằng lời gọi đọc sau lưu và sử dụng cấu hình transaction được giải thích ở phần sau.

### 7.2. Đọc: xử lý kết quả vắng mặt một cách rõ ràng

~~~java
StudyTask loaded = repository.findById(id)
    .orElseThrow(() -> new IllegalStateException(
        "Không tìm thấy nhiệm vụ: " + id
    ));
~~~

`findById` trả về `Optional<StudyTask>`:

- Có dữ liệu: `Optional` chứa đối tượng.
- Không có dữ liệu: `Optional.empty()`.
- Lỗi truy cập dữ liệu: có thể phát sinh exception; không được hiểu là một kết quả vắng mặt bình thường.

Trong bài thực hành, không tìm thấy ngay sau lưu là một điều kiện thất bại, nên dùng `orElseThrow`. Trong luồng nghiệp vụ thực tế, đối tượng không tồn tại có thể là tình huống bình thường và cần cách xử lý phù hợp với yêu cầu của ứng dụng.

Không truyền `null` làm ID, và không dùng `Optional.get()` mà không xác định rõ cách xử lý trường hợp rỗng.

### 7.3. Sửa: tìm theo ID, thay đổi thuộc tính rồi lưu

~~~java
loaded.rename(updatedTitle);
loaded.markCompleted();

StudyTask updated = repository.save(loaded);
~~~

Ta cập nhật chính đối tượng đã tìm theo ID để giữ rõ ý nghĩa: thay đổi trạng thái của một nhiệm vụ đang tồn tại.

Không tạo một `StudyTask` hoàn toàn mới rồi gọi `save` và kỳ vọng nó tự tìm đối tượng cũ theo tiêu đề. Trong ví dụ, một đối tượng mới có ID bằng `null` được xem là đối tượng mới theo cơ chế nhận diện mặc định phù hợp với mapping đang dùng.

Tương tự, không suy ra rằng tự gán một ID bất kỳ sẽ biến mọi thao tác lưu thành cập nhật an toàn. Việc nhận diện đối tượng mới, xử lý ID và kiểm tra version phụ thuộc module cùng cấu hình domain.

Sau khi lưu, lần đọc tiếp theo xác nhận hai điều độc lập:

- Vẫn là đối tượng có cùng định danh.
- Tiêu đề và trạng thái lưu trữ đã phản ánh giá trị mới.

### 7.4. Xóa: dùng ID đã nhận rồi đọc lại

~~~java
repository.deleteById(id);

boolean stillPresent = repository.findById(id).isPresent();
~~~

Bài thực hành chỉ xóa ID do chính vòng này tạo ra. Không cần `deleteAll()` hoặc xóa dữ liệu khác để đạt mục tiêu.

`deleteById` không trả về một đối tượng dùng để chứng minh kết quả xóa. Do đó, kiểm chứng bằng lần tìm tiếp theo có giá trị hơn việc chỉ quan sát method không ném exception.

Không dùng kỳ vọng “xóa một ID không tồn tại nhất định phải ném exception” làm tiêu chí chung cho mọi phiên bản hay mọi module Spring Data. Vòng thực hành bắt đầu từ một đối tượng đã được tạo và đọc lại rõ ràng.

## 8. Hiểu transaction để tránh kết luận sai

### 8.1. Vì sao runner không có transaction bao ngoài?

Bean runner trong ví dụ không được bọc bởi một transaction bao trùm toàn bộ vòng CRUD. Với cấu hình mặc định của Spring Data JPA cho các method CRUD kế thừa được dùng ở đây:

- Lời gọi lưu có transaction ghi tương ứng.
- Lời gọi đọc có transaction đọc tương ứng.
- Lời gọi xóa có transaction ghi tương ứng.

Khi không có transaction bao ngoài, các lời gọi này hoàn tất phạm vi transaction của chúng trước khi bước tiếp theo được gọi. Với ứng dụng console và cấu hình mặc định của ví dụ, entity đọc ra cũng không được giữ trong một persistence context xuyên suốt toàn bộ runner.

Cách tổ chức này giúp người mới quan sát riêng từng thao tác. Nó không có nghĩa nghiệp vụ thật nên luôn chia mỗi method repository thành một transaction độc lập.

Nếu một nghiệp vụ cần tất cả thay đổi cùng thành công hoặc cùng rollback, ranh giới transaction thường phải đặt quanh cả nghiệp vụ đó, với khả năng của công nghệ lưu trữ được chọn.

### 8.2. Đọc lại trong cùng persistence context có thể gây hiểu nhầm

Nếu đặt toàn bộ vòng vào một transaction JPA duy nhất, một lần `findById` tiếp theo có thể lấy entity đã được quản lý từ persistence context. Việc thấy tiêu đề mới khi đó chưa nhất thiết chứng minh một vòng đọc độc lập từ cơ sở dữ liệu đã diễn ra.

JPA cũng có cơ chế dirty checking: entity đang được quản lý có thể được ghi nhận thay đổi khi transaction hoàn tất mà không cần gọi `save` lần nữa. Tuy nhiên, đó là hành vi của JPA trong điều kiện entity còn được quản lý, không phải quy tắc chung của `CrudRepository`.

Trong bài này, ta chủ động gọi `save` sau khi sửa và đọc lại ở bước tiếp theo để thể hiện đủ vòng CRUD, không dựa vào một persistence context bao ngoài.

### 8.3. Flush và commit có ý nghĩa khác nhau

- **Flush** đồng bộ những thay đổi đang chờ trong persistence context xuống cơ sở dữ liệu.
- **Commit** hoàn tất transaction thành công.
- Một thay đổi đã flush vẫn có thể bị rollback trước khi transaction kết thúc.

`CrudRepository` không cung cấp một quy tắc “save luôn flush và commit ngay” cho mọi kho dữ liệu. Nếu lời gọi repository đang tham gia một transaction lớn hơn, việc commit còn phụ thuộc transaction bao ngoài đó.

Không cần thêm `saveAndFlush` để hoàn thành bài này. Nếu ứng dụng thực tế cần điều khiển flush, đó là lúc đánh giá khả năng chuyên biệt của module JPA.

## 9. Những lỗi dễ gặp khi chạy bài

| Hiện tượng | Nguyên nhân có thể có | Cách kiểm tra |
| --- | --- | --- |
| Không inject được `StudyTaskRepository`. | Thiếu module JPA, repository ngoài phạm vi quét hoặc cấu hình chưa phù hợp. | Kiểm tra dependency, package cha của ứng dụng và package repository. |
| Entity không được JPA quản lý. | Thiếu `@Entity`, package entity ngoài phạm vi phát hiện hoặc trộn namespace JPA. | Đối chiếu import và vị trí entity. |
| Lỗi không có constructor phù hợp. | Thiếu constructor không tham số phục vụ JPA. | Giữ constructor `protected StudyTask()`. |
| ID không được sinh như dự kiến. | Mapping ID, schema hoặc khả năng của cơ sở dữ liệu không phù hợp. | Kiểm tra `@Id`, `@GeneratedValue` và cấu hình datasource. |
| Sửa biến Java nhưng đọc lại vẫn là dữ liệu cũ. | Chưa lưu thay đổi trong mô hình đang dùng hoặc đọc ở sai môi trường. | Kiểm tra lời gọi `save`, transaction và datasource. |
| Sau cập nhật lại có thêm một dòng. | Đã tạo entity mới không có ID thay vì sửa entity đọc ra. | Giữ ID từ kết quả lưu và cập nhật đối tượng tương ứng. |
| Chạy lại ứng dụng không còn dữ liệu cũ. | H2 trong bộ nhớ và schema được tạo/dọn theo cấu hình bài. | Phân biệt vòng đời JVM với việc đọc lại trong cùng lần chạy. |
| Không thấy dòng `CRUD_CYCLE=PASS`. | Một bước kiểm chứng hoặc khởi tạo đã thất bại. | Đọc exception đầu tiên có nguyên nhân liên quan, không chỉ nhìn dòng log cuối. |

Đọc kết quả với đúng ngữ cảnh. Việc không tìm thấy dữ liệu sau khi đã đóng ứng dụng không chứng minh rằng thao tác lưu trước đó thất bại; đây là môi trường thực hành trong bộ nhớ và ví dụ đã chủ động đóng context.

## 10. Phần nào thuộc Commons, phần nào thuộc JPA/H2?

| Thành phần trong bài | Vai trò |
| --- | --- |
| `CrudRepository<StudyTask, Long>` | Hợp đồng CRUD dùng chung của Spring Data Commons. |
| `save`, `findById`, `deleteById` | Các thao tác được diễn đạt qua hợp đồng repository. |
| `Optional` | Kiểu Java dùng để biểu diễn kết quả có hoặc không trong hợp đồng tìm theo ID. |
| `@Entity`, `@Table`, `@GeneratedValue` | Mapping và sinh ID theo JPA. |
| Repository proxy và triển khai truy cập JPA | Được tích hợp bởi module Spring Data JPA trên hạ tầng chung. |
| H2 và câu lệnh SQL quan sát được | Kho dữ liệu và cơ chế thực thi của ví dụ. |
| Persistence context, dirty checking và flush | Khái niệm đặc thù JPA liên quan đến cách dữ liệu được quản lý. |
| `ApplicationRunner` và vòng đời ứng dụng | Cơ chế chạy ví dụ của Spring Boot. |

Nếu chuyển bài sang một module Spring Data khác có hỗ trợ repository tương ứng, vẫn có thể giữ tư duy lưu–đọc–sửa–xóa. Tuy nhiên, cần đánh giá lại kiểu ID, mapping, cách nhận diện đối tượng mới, cơ chế cập nhật, transaction và độ nhất quán khi đọc sau ghi.

Không mặc định rằng dùng cùng tên `save` sẽ tạo ra cùng câu lệnh, cùng cách cập nhật một phần đối tượng hay cùng thời điểm dữ liệu có thể được nhìn thấy từ nơi khác.

## 11. Bài tập củng cố

### Bài tập 1: Thay đổi giá trị nghiệp vụ

Đổi tiêu đề ban đầu và tiêu đề sau cập nhật. Chạy lại vòng thực hành và đối chiếu:

- Dòng đọc đầu phải có tiêu đề ban đầu.
- Dòng đọc sau cập nhật phải có tiêu đề mới.
- ID phải giữ nguyên trong suốt vòng.
- Sau xóa, lần tìm theo ID phải không có kết quả.

Không thay ID bằng một con số cố định để làm bài chạy qua.

### Bài tập 2: Quan sát khác biệt giữa bộ nhớ và kho dữ liệu

Trong một biến thể của runner, sau khi đọc được entity, chỉ gọi `rename` nhưng tạm bỏ lời gọi `save` cập nhật. Giữ cấu hình runner không có transaction bao ngoài như ví dụ.

Đọc lại theo ID và so sánh dữ liệu đọc được với biến Java vừa sửa. Với cấu hình JPA chuẩn của bài, thay đổi trên đối tượng đã tách khỏi persistence context không tự trở thành một cập nhật đã lưu.

Khôi phục lời gọi `save` sau khi quan sát. Nếu bạn thêm transaction bao ngoài, hành vi có thể khác do dirty checking; đó chính là lý do phải mô tả điều kiện của thí nghiệm.

### Bài tập 3: Xử lý đối tượng không còn tồn tại

Sau khi xóa, thử thiết kế cách thông báo “không tìm thấy nhiệm vụ” từ `Optional.empty()` mà không dùng `Optional.get()` trực tiếp.

Phân biệt rõ tình huống không có dữ liệu với tình huống lỗi kết nối hoặc lỗi truy vấn. Hai trường hợp cần được biểu diễn và xử lý khác nhau trong ứng dụng.

## 12. Tiêu chí tự đối chiếu kết quả

| Mốc kiểm chứng | Điều cần thấy |
| --- | --- |
| Trước lưu | Đối tượng mới chưa có ID và chưa hoàn thành. |
| Sau lưu | Dùng đối tượng `save` trả về, lấy được ID để tiếp tục. |
| Sau đọc | Tìm được đúng tiêu đề ban đầu bằng ID vừa nhận. |
| Sau sửa và lưu | Định danh giữ nguyên, dữ liệu mới được gửi qua repository. |
| Sau đọc lại | Tiêu đề và trạng thái hoàn thành phản ánh giá trị cập nhật. |
| Sau xóa | `findById` trả về kết quả rỗng cho chính ID của vòng thực hành. |

Khi những mốc này đạt, bạn đã quan sát được một vòng CRUD qua hợp đồng Spring Data Commons trên một công nghệ lưu trữ cụ thể. Từ nền tảng đó, các bài về derived queries, phân trang, projection và auditing có thể bổ sung cách tìm kiếm hoặc quản lý metadata mà vẫn dựa trên mô hình repository đã thực hành.