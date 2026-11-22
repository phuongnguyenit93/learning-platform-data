# Phân biệt sắp xếp bằng OrderBy và lưu vị trí bằng OrderColumn trong JPA

Trong Jakarta Persistence (JPA), một thuộc tính tập hợp như `List<Book>`, `List<String>`, `Set<Tag>` hoặc `Map<String, Item>` có thể biểu diễn các phần tử liên quan đến một entity. Tuy nhiên, **thứ tự hiển thị phần tử** và **vị trí của phần tử được lưu thành dữ liệu** là hai yêu cầu khác nhau.

- **`@OrderBy`** yêu cầu JPA **sắp xếp các phần tử khi tải collection**, dựa vào giá trị thuộc tính đã được ánh xạ, chẳng hạn `title ASC` hoặc `createdAt DESC`. Nó không mặc nhiên tạo cột vị trí để ghi thứ tự người dùng kéo thả.
- **`@OrderColumn`** yêu cầu JPA **lưu vị trí (index) của từng phần tử trong danh sách** vào cột riêng. Khi thêm, xóa hoặc đổi vị trí phần tử của một `List` được quản lý, provider duy trì các chỉ số này để lần tải sau tái tạo đúng thứ tự.

Đây không phải hai annotation có thể đổi cho nhau: một bên là **thứ tự suy ra từ giá trị dữ liệu**, bên kia là **thứ tự là chính dữ liệu cần lưu trữ**.

Bài học đặt hai cách vào ngữ cảnh **Data Persistence, Relational Access, ORM JPA**, chương **Tập hợp và Map**. Ngoài các ví dụ thực hành, ta sẽ xem ảnh hưởng tới SQL, schema, vòng đời transaction, cập nhật thứ tự, hiệu năng và sự khác nhau giữa `List`, `Set` với `Map`.

## 1. Ví dụ phân biệt ngay từ yêu cầu nghiệp vụ

Một thư viện có 4 cuốn sách:

| ID | Tên sách | Ngày thêm |
| ---: | --- | --- |
| 17 | Algorithms | 2026-10-03 |
| 22 | Databases | 2026-10-01 |
| 31 | Java Persistence | 2026-10-02 |
| 45 | Networking | 2026-10-05 |

Có ít nhất hai yêu cầu hoàn toàn khác:

**Yêu cầu A — Danh sách luôn sắp theo tên sách tăng dần.** Người dùng không thể thay đổi thứ tự thủ công; khi tên sách thay đổi, lần tải tiếp theo phải sắp xếp lại theo tên mới. Đây là trường hợp điển hình của **`@OrderBy("title ASC")`**.

**Yêu cầu B — Người dùng tạo danh sách đọc với thứ tự tự chọn.** Họ kéo cuốn “Java Persistence” lên vị trí đầu tiên, dù nó không đứng đầu theo bảng chữ cái. Thứ tự tùy chọn phải còn nguyên sau khi đăng xuất và đăng nhập lại. Đây là trường hợp **`@OrderColumn`**, vì vị trí 0, 1, 2, 3 là một phần của dữ liệu nghiệp vụ.

~~~text
DANH SÁCH THEO THUỘC TÍNH                 DANH SÁCH CÓ VỊ TRÍ LƯU
@OrderBy("title ASC")                      @OrderColumn(name = "position_idx")

     Algorithms                                  [0] Java Persistence
     Databases                                   [1] Algorithms
     Java Persistence                            [2] Networking
     Networking                                  [3] Databases

Thứ tự = hàm của title                      Thứ tự = giá trị index đã lưu
Thay title -> kết quả sort đổi                Kéo-thả -> UPDATE position_idx
~~~

**Nguyên tắc chọn nhanh:** nếu có thể tính thứ tự từ một hoặc nhiều cột dữ liệu hiện có, chọn `@OrderBy` hoặc một truy vấn `ORDER BY`. Nếu thứ tự do người dùng hoặc quy trình nghiệp vụ gán **độc lập với các thuộc tính nội dung**, cần mô hình lưu vị trí, thường bằng `@OrderColumn` với `List`.

## 2. Không có annotation thì List có được lưu thứ tự không?

Trong Java, `List` có thứ tự phần tử, còn `Set` không mô tả thứ tự vị trí theo chỉ số. Nhưng **thứ tự của một `List` trong bộ nhớ không tự biến thành cột thứ tự của database**.

Ví dụ:

~~~java
@OneToMany(mappedBy = "library")
private List<Book> books = new ArrayList<>();
~~~

Câu lệnh Java:

~~~java
books.add(bookA);
books.add(bookB);
books.add(0, bookC);
~~~

chỉ làm thay đổi **cấu trúc List đang sử dụng trong bộ nhớ**. Nếu mapping và schema không có cơ chế lưu thứ tự, việc tải lại collection ở một persistence context khác **không được giả định** sẽ giữ thứ tự Java trước đó.

Cơ sở dữ liệu quan hệ cũng không cam kết thứ tự các dòng khi câu truy vấn không có `ORDER BY`. Việc một lần truy vấn tình cờ trả theo ID, thời điểm insert hoặc thứ tự index **không phải hợp đồng dữ liệu**.

| Cấu trúc Java | Thứ tự trong bộ nhớ | Thứ tự sau khi tải từ DB nếu không có mapping/truy vấn sắp xếp |
| --- | --- | --- |
| `List<E>` | Có vị trí `0..n-1` | Không nên giả định giữ thứ tự ban đầu |
| `Set<E>` | Không có vị trí index theo hợp đồng `Set` | Không nên giả định thứ tự duyệt |
| `Map<K,V>` | Truy cập bằng key | Không nên giả định thứ tự lặp entry theo key hoặc theo lần insert |
| `SortedSet<E>` / `SortedMap<K,V>` | Có quy tắc so sánh riêng của Java | Không đồng nghĩa provider đã lưu vị trí hay sắp SQL theo cùng tiêu chí |

JPA có các lựa chọn để làm rõ nhu cầu **sort theo thuộc tính**, **lưu index**, hoặc **tự thiết kế cột thứ tự nghiệp vụ**.

## 3. @OrderBy: sắp xếp theo thuộc tính đã ánh xạ

### 3.1. Ý nghĩa annotation

`jakarta.persistence.OrderBy` khai báo một biểu thức sắp xếp cho các phần tử được tải từ collection. Với collection entity, biểu thức dùng **tên thuộc tính Java** của entity đích, không phải tên cột SQL vật lý.

Ví dụ:

~~~java
@OneToMany(mappedBy = "library")
@OrderBy("title ASC, id ASC")
private List<Book> books = new ArrayList<>();
~~~

Khi cần tải collection, provider có thể sinh SQL với phần `ORDER BY` tương ứng:

~~~sql
SELECT b.*
FROM books b
WHERE b.library_id = ?
ORDER BY b.title ASC, b.id ASC;
~~~

SQL trên là **minh họa**, không phải chuỗi câu lệnh bắt buộc của mọi provider. Nhưng mục tiêu của mapping là: khi materialize collection, thứ tự phần tử được xác định từ giá trị trường `title`, rồi từ `id` khi các title trùng nhau.

**`@OrderBy` không thêm cột `position` vào bảng.** Nếu một cuốn sách đổi tên, thứ tự khi collection được tải mới có thể đổi dù không có bất kỳ thao tác reorder nào trên `List`.

### 3.2. Ví dụ entity Book và Library

Ví dụ dùng Java 17+, Jakarta Persistence 3.x:

~~~java
package com.example.library.domain;

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
@Table(name = "books")
public class Book {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "title", nullable = false, length = 200)
    private String title;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "library_id", nullable = false)
    private Library library;

    protected Book() {
    }

    public Book(String title) {
        this.title = title;
    }

    void attachTo(Library library) {
        this.library = library;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public void rename(String newTitle) {
        if (newTitle == null || newTitle.isBlank()) {
            throw new IllegalArgumentException("Title must not be blank");
        }
        this.title = newTitle;
    }
}
~~~

Parent:

~~~java
package com.example.library.domain;

import jakarta.persistence.CascadeType;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.OneToMany;
import jakarta.persistence.OrderBy;
import jakarta.persistence.Table;
import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "libraries")
public class Library {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 120)
    private String name;

    @OneToMany(mappedBy = "library", cascade = CascadeType.PERSIST)
    @OrderBy("title ASC, id ASC")
    private List<Book> books = new ArrayList<>();

    protected Library() {
    }

    public Library(String name) {
        this.name = name;
    }

    public void addBook(Book book) {
        if (book == null) {
            throw new IllegalArgumentException("Book must not be null");
        }
        books.add(book);
        book.attachTo(this);
    }

    public List<Book> getBooks() {
        return books;
    }
}
~~~

Schema phù hợp:

~~~sql
CREATE TABLE libraries (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(120) NOT NULL
);

CREATE TABLE books (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    library_id BIGINT NOT NULL,
    title VARCHAR(200) NOT NULL,
    FOREIGN KEY (library_id) REFERENCES libraries(id)
);

CREATE INDEX idx_books_library_title_id
    ON books (library_id, title, id);
~~~

Chú ý `@OrderBy("title ASC, id ASC")` sử dụng **`title` và `id`**, không dùng `books.title` hoặc `books.id` vì expression được viết theo thuộc tính của entity phần tử. JPA kết hợp chúng với điều kiện lấy phần tử thuộc collection.

### 3.3. ASC, DESC và nhiều tiêu chí

~~~java
@OrderBy("createdAt DESC")
private List<Comment> comments;
~~~

Có thể kết hợp nhiều tiêu chí:

~~~java
@OrderBy("priority DESC, createdAt ASC, id ASC")
private List<Task> tasks;
~~~

Các thuộc tính `priority`, `createdAt` và `id` phải tồn tại và được mapping trên entity phần tử. `ASC` là chiều tăng, `DESC` là chiều giảm; nếu bỏ hướng ở một thuộc tính, hướng mặc định là tăng.

Thêm một tiêu chí phân biệt duy nhất như ID thường hữu ích: nếu hai phần tử có cùng `title`, database không bắt buộc trả chúng theo thứ tự ổn định trừ khi còn điều kiện `ORDER BY` bổ sung.

### 3.4. @OrderBy không tự sắp lại List ngay sau khi sửa Java

Giả sử đã tải `library.getBooks()` theo `title ASC`. Sau đó code:

~~~java
Book book = library.getBooks().get(0);
book.rename("ZZZ - New Title");
~~~

Không nên giả định collection trong **cùng persistence context và cùng List instance** sẽ ngay lập tức được sắp lại sau khi setter chạy. `@OrderBy` quy định thứ tự **khi dữ liệu được truy xuất/materialize**; nó không biến `ArrayList` thành một cấu trúc liên tục tự sort trong bộ nhớ.

Tùy cách thao tác và provider, bạn có thể cần sort collection đang dùng bằng Java để hiển thị tức thời, hoặc tải lại ở một context mới sau khi flush/commit nếu muốn dựa vào thứ tự do SQL trả về.

Ngược lại, thao tác:

~~~java
java.util.Collections.swap(
    library.getBooks(), 0, 1
);
~~~

chỉ đổi vị trí của hai phần tử trong List hiện tại. Với mapping `@OrderBy` thuần, thao tác đó **không tạo yêu cầu lưu chỉ số vị trí** cho database. Lần tải mới vẫn sắp theo `title` và `id`.

## 4. @OrderColumn: thứ tự như dữ liệu có vị trí

### 4.1. Vai trò và ngữ nghĩa

`jakarta.persistence.OrderColumn` dùng với **collection có thứ tự kiểu List** được mapping phù hợp, chẳng hạn `@ElementCollection` hoặc quan hệ collection. Nó yêu cầu provider lưu chỉ số của các phần tử vào một **order column**.

Ví dụ:

~~~java
@ElementCollection
@CollectionTable(
    name = "reading_list_items",
    joinColumns = @JoinColumn(name = "reading_list_id")
)
@OrderColumn(name = "position_idx")
@Column(name = "book_title", nullable = false)
private List<String> titles = new ArrayList<>();
~~~

Đây là mô hình **danh sách các giá trị String** trong `ReadingList`; mỗi phần tử có một vị trí được ghi vào `reading_list_items.position_idx`.

| `reading_list_id` | `position_idx` | `book_title` |
| ---: | ---: | --- |
| 50 | 0 | Java Persistence |
| 50 | 1 | Algorithms |
| 50 | 2 | Networking |

Dữ liệu có ý nghĩa: tại `ReadingList#50`, phần tử ở vị trí 0 là `Java Persistence`, vị trí 1 là `Algorithms`, và vị trí 2 là `Networking`.

Trong các ánh xạ danh sách có `@OrderColumn`, provider có trách nhiệm duy trì thứ tự vị trí theo cơ chế mà JPA quy định. Chỉ số danh sách JPA được đánh số **từ 0**; cột thứ tự là một cột số nguyên thích hợp, không phải thuộc tính sắp xếp tùy ý của `String`.

### 4.2. Ví dụ hoàn chỉnh với @ElementCollection

~~~java
package com.example.library.domain;

import jakarta.persistence.CollectionTable;
import jakarta.persistence.Column;
import jakarta.persistence.ElementCollection;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.OrderColumn;
import jakarta.persistence.Table;
import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "reading_lists")
public class ReadingList {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "owner_name", nullable = false, length = 120)
    private String ownerName;

    @ElementCollection
    @CollectionTable(
        name = "reading_list_items",
        joinColumns = @JoinColumn(name = "reading_list_id")
    )
    @OrderColumn(name = "position_idx")
    @Column(name = "book_title", nullable = false, length = 200)
    private List<String> titles = new ArrayList<>();

    protected ReadingList() {
    }

    public ReadingList(String ownerName) {
        this.ownerName = ownerName;
    }

    public void addTitle(String title) {
        if (title == null || title.isBlank()) {
            throw new IllegalArgumentException("Title must not be blank");
        }
        titles.add(title);
    }

    public void moveTitle(int fromIndex, int toIndex) {
        if (fromIndex < 0 || fromIndex >= titles.size()
                || toIndex < 0 || toIndex >= titles.size()) {
            throw new IndexOutOfBoundsException("Invalid position");
        }
        String title = titles.remove(fromIndex);
        titles.add(toIndex, title);
    }

    public void removeTitle(int index) {
        titles.remove(index);
    }

    public List<String> getTitles() {
        return java.util.Collections.unmodifiableList(titles);
    }
}
~~~

Schema tương ứng:

~~~sql
CREATE TABLE reading_lists (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    owner_name VARCHAR(120) NOT NULL
);

CREATE TABLE reading_list_items (
    reading_list_id BIGINT NOT NULL,
    position_idx INTEGER NOT NULL,
    book_title VARCHAR(200) NOT NULL,
    PRIMARY KEY (reading_list_id, position_idx),
    FOREIGN KEY (reading_list_id)
        REFERENCES reading_lists(id)
);
~~~

Đây là schema minh họa **thứ tự được lưu**. Primary key ghép `(reading_list_id, position_idx)` giúp một List không có hai dòng cùng vị trí, nhưng không tự đảm bảo không có khoảng trống vị trí; việc duy trì chuỗi index hợp lệ là trách nhiệm của application/provider và quy trình ghi dữ liệu.

Các phần tử trong ví dụ là **giá trị cơ bản**, không phải entity có ID riêng. Điều này phù hợp nếu một danh sách chỉ lưu các nhãn hoặc tên sách, và việc sửa/xóa theo vị trí là đủ. Nếu mỗi phần tử cần ID, trạng thái và quan hệ riêng, hãy dùng entity cho item thay vì chỉ `String`.

### 4.3. Thay đổi thứ tự dẫn tới SQL như thế nào?

Giả sử một `ReadingList` đang managed có:

~~~text
[0] Java Persistence
[1] Algorithms
[2] Networking
~~~

Đổi từ vị trí 2 lên vị trí 0:

~~~java
em.getTransaction().begin();

ReadingList readingList = em.find(ReadingList.class, 50L);
readingList.moveTitle(2, 0);

em.getTransaction().commit();
~~~

Trong memory:

~~~text
[0] Networking
[1] Java Persistence
[2] Algorithms
~~~

Khi flush, provider phải đồng bộ collection để lần tải sau phản ánh đúng thứ tự. Với `@ElementCollection`, tùy provider và mapping, có thể xuất hiện **DELETE/INSERT lại hàng** hoặc **UPDATE vị trí**, không nhất thiết chỉ một SQL UPDATE cho phần tử được chuyển.

SQL mang ý tưởng dữ liệu, không khẳng định chính xác cách provider thực hiện:

~~~sql
-- Có thể thay đổi các hàng theo position_idx,
-- hoặc xóa/chèn lại một phần collection.
-- Trạng thái cuối cùng cần có:
-- 50,0,'Networking'
-- 50,1,'Java Persistence'
-- 50,2,'Algorithms'
~~~

**`@OrderColumn` tạo thêm công việc ghi dữ liệu khi reorder.** Với danh sách dài, chèn/xóa ở đầu hoặc giữa có thể ảnh hưởng vị trí nhiều phần tử và phát sinh nhiều SQL hơn thao tác append ở cuối.

### 4.4. Cột order không phải field nghiệp vụ của item

Trong mapping `@OrderColumn`, cột `position_idx` được provider quản lý để biểu diễn **vị trí phần tử trong List**. Nó không nhất thiết được ánh xạ vào field `position` của entity item.

Nếu cùng một cột vừa được `@OrderColumn` quản lý, vừa được một thuộc tính entity khác tự cập nhật, có thể tạo **hai nguồn ghi cạnh tranh** hoặc lỗi mapping trùng cột. Khi cần vị trí như thuộc tính nghiệp vụ để query/sửa riêng, nên cân nhắc một chiến lược rõ ràng: dùng order column do JPA quản lý, hoặc dùng trường `position` do ứng dụng quản lý và truy vấn `@OrderBy` theo trường đó.

## 5. So sánh trực tiếp @OrderBy và @OrderColumn

| Tiêu chí | `@OrderBy` | `@OrderColumn` |
| --- | --- | --- |
| Mục đích | Sắp xếp collection theo giá trị thuộc tính | Lưu thứ tự vị trí của phần tử trong List |
| Đầu vào thứ tự | `title`, `createdAt`, `priority`, v.v. | Index do thứ tự List xác định |
| Dữ liệu bổ sung cần lưu | Không bắt buộc có cột vị trí | Có cột số biểu diễn vị trí |
| Ví dụ annotation | `@OrderBy("title ASC")` | `@OrderColumn(name="position_idx")` |
| Thay đổi tên/thuộc tính sắp xếp | Có thể đổi thứ tự khi tải mới | Không tự đổi vị trí nếu List chưa được reorder |
| `Collections.swap(...)`/`list.add(0, ...)` | Không tự bảo đảm lưu thứ tự thủ công | Có thể dẫn tới cập nhật vị trí |
| Kiểu collection đặc trưng | Collection entity, `List`/`Set`; có quy tắc áp dụng với element collection và Map | `List` cần lưu vị trí; không dùng để tạo index cho `Set`/`Map` |
| SQL khi đọc | Thường có `ORDER BY` theo thuộc tính | Đọc theo order column để tái tạo List |
| SQL khi reorder | Không có cột index để cập nhật | Có thể UPDATE nhiều vị trí hoặc ghi lại collection |
| Trùng giá trị sort | Có thể cần tiêu chí phụ để có thứ tự ổn định | Mỗi vị trí trong một list được phân biệt bằng index |
| Chèn ở giữa danh sách | Không phải thao tác nghiệp vụ lưu vị trí | Dễ phải cập nhật các index phía sau |
| Rủi ro hiệu năng | SORT/index theo cột lọc và sort | Write amplification, unique constraint khi hoán đổi index |
| Phù hợp | Danh sách sorted cố định theo business field | Playlist, thứ tự bước, mục kéo-thả, nội dung có thứ tự tùy chọn |

Một câu kiểm tra thiết kế hữu ích: **“Nếu đổi tên mục mà không kéo thả gì, có muốn thứ tự thay đổi không?”** Nếu có, chọn kiểu sắp theo thuộc tính. Nếu không, nhưng thao tác kéo thả phải còn hiệu lực qua các lần tải, cần lưu vị trí.

## 6. @OrderBy trên List, Set và các kiểu khác

### 6.1. List: dữ liệu được tải theo giá trị sort

~~~java
@OneToMany(mappedBy = "library")
@OrderBy("title ASC, id ASC")
private List<Book> books = new ArrayList<>();
~~~

`List` cho phép truy cập theo chỉ số sau khi collection được tải. Nhưng chỉ số ở đây **là vị trí trong kết quả sắp theo title**, không phải khóa vị trí đã ghi vào DB.

Ví dụ:

~~~java
Book firstBook = library.getBooks().get(0);
~~~

Nếu có cuốn sách mới với `title` đứng trước những cuốn cũ, lần tải sau `firstBook` có thể thay đổi. Vì vậy không dùng `List index` như ID hay vị trí nghiệp vụ ổn định khi chỉ có `@OrderBy`.

### 6.2. Set: sắp xếp khi truy xuất không tạo thứ tự index

~~~java
@OneToMany(mappedBy = "library")
@OrderBy("title ASC, id ASC")
private Set<Book> books = new LinkedHashSet<>();
~~~

Có thể yêu cầu JPA truy xuất theo thứ tự thuộc tính khi mapping hỗ trợ. Tuy nhiên, `Set` không có `get(0)` và không biểu diễn index kiểu `List`. Nếu ứng dụng cần vị trí 0/1/2 có thể kéo-thả, `Set` không phải cấu trúc phù hợp cho `@OrderColumn`.

Cần phân biệt thêm: thứ tự SQL khi tải, thứ tự duyệt của một implementation `Set` trong bộ nhớ, và **sorted set** theo `Comparator`/`Comparable` của Java là các khái niệm khác nhau. Không suy ra mọi `HashSet` sẽ duyệt theo thứ tự mà SQL vừa trả về. Trong ứng dụng cần thứ tự duyệt ổn định, nên chọn kiểu và cách load phù hợp với provider/contract, hoặc trả về `List` ở lớp đọc dữ liệu.

### 6.3. Element collection của basic value

Với collection `String`:

~~~java
@ElementCollection
@CollectionTable(
    name = "library_topics",
    joinColumns = @JoinColumn(name = "library_id")
)
@Column(name = "topic")
@OrderBy
private List<String> topics = new ArrayList<>();
~~~

JPA có cơ chế sắp xếp theo **giá trị phần tử cơ bản** khi `@OrderBy` áp dụng cho element collection of basic type. Ở trường hợp basic element này, chuỗi biểu thức trong annotation không được dùng theo cách chỉ tên field entity như `title`, vì bản thân phần tử là `String`, không có property `title`.

Nếu muốn danh sách thẻ/từ khóa chỉ sắp theo giá trị chữ cái, đây là hướng có thể cân nhắc. Nếu muốn lưu thứ tự người dùng tự gán, `@OrderColumn` trên `List<String>` như ví dụ `ReadingList` thích hợp hơn.

### 6.4. Embeddable trong element collection

Với `List<Address>` hoặc `List<StepDetail>` được khai báo `@ElementCollection`, có thể có những trường trong embeddable dùng để sắp theo thuộc tính, hoặc có order column để lưu vị trí. Khi chọn tiêu chí `@OrderBy`, biểu thức tham chiếu **tên thuộc tính được ánh xạ của embeddable** theo các quy tắc JPA. Khi dùng `@OrderColumn`, thứ tự do List điều khiển ngay cả khi hai embeddable có cùng giá trị ở các trường thường.

Trong mọi trường hợp, **embeddable không phải entity riêng có ID**, nên không được suy ra rằng có thể dùng `EntityManager.find(Embeddable.class, ...)` để tải một phần tử theo vị trí.

## 7. Map: khóa tra cứu không phải vị trí của List

Một `Map<K,V>` quản lý phần tử bằng **key**, không bằng chỉ số `0, 1, 2...`. Trong JPA, Map collection có các mapping như `@MapKey` hoặc `@MapKeyColumn` để xác định dữ liệu làm key.

Ví dụ một entity có Map cấu hình theo ngôn ngữ:

~~~java
@Entity
@Table(name = "catalogs")
public class Catalog {

    @Id
    private Long id;

    @ElementCollection
    @CollectionTable(
        name = "catalog_translations",
        joinColumns = @JoinColumn(name = "catalog_id")
    )
    @MapKeyColumn(name = "locale_code", length = 10)
    @Column(name = "display_name", length = 200)
    private Map<String, String> displayNames = new HashMap<>();

    protected Catalog() {
    }
}
~~~

Schema tương ứng:

~~~sql
CREATE TABLE catalog_translations (
    catalog_id BIGINT NOT NULL,
    locale_code VARCHAR(10) NOT NULL,
    display_name VARCHAR(200),
    PRIMARY KEY (catalog_id, locale_code),
    FOREIGN KEY (catalog_id) REFERENCES catalogs(id)
);
~~~

| `catalog_id` | `locale_code` (map key) | `display_name` (map value) |
| ---: | --- | --- |
| 7 | en | Book |
| 7 | vi | Sách |
| 7 | ja | 本 |

Dùng:

~~~java
String vietnamese = catalog.getDisplayNames().get("vi");
~~~

Ở đây:

- `@MapKeyColumn(name="locale_code")` lưu **key** của Map.
- `@Column(name="display_name")` lưu **value**.
- `@OrderColumn` không phải cơ chế để tạo ra một chỉ số cho Map.
- `Map` không tự bảo đảm thứ tự lặp theo key như một `List` theo position.

**`@MapKeyColumn` không phải `@OrderColumn`.** Map key có ý nghĩa nhận diện entry; List index có ý nghĩa vị trí. Hai giá trị có thể tình cờ là số nguyên, nhưng hợp đồng thao tác và mục đích ánh xạ khác hẳn.

### 7.1. Có thể sắp Map bằng @OrderBy không?

Trong những mapping Map mà JPA cho phép dùng `@OrderBy`, biểu thức sắp xếp áp dụng cho **giá trị (value) trong Map**, không mặc nhiên sắp theo map key. Ví dụ với `Map<String, Book>` được ánh xạ theo một thuộc tính key và association tới các Book, việc ghi `@OrderBy("title ASC")` có ý nghĩa yêu cầu sắp phần tử value theo `Book.title` khi truy xuất.

Dù vậy, nếu ứng dụng cần **hợp đồng thứ tự lặp entry theo key** hoặc một thứ tự hiển thị ổn định, không nên dựa vào cách một `HashMap` cụ thể được khởi tạo. Có thể:

1. Query các entry hoặc các value thành `List` có `ORDER BY` rõ ràng theo tiêu chí mong muốn.
2. Ở tầng ứng dụng, chuyển sang `LinkedHashMap` hoặc `TreeMap` khi quy tắc sắp xếp và kiểu key thích hợp.
3. Nếu thứ tự entry là dữ liệu người dùng được phép kéo-thả, mô hình hóa một **List của các item có key và position**, thay vì ép một Map thành danh sách có index.

Với `TreeMap`, comparator Java quy định thứ tự key **trong bộ nhớ**; nó không tự tạo thêm cột vị trí hay thay đổi cách DB lưu collection.

## 8. Khi @OrderColumn dùng với quan hệ OneToMany

Ngoài `@ElementCollection`, `@OrderColumn` còn được dùng trên `List` của quan hệ `@OneToMany` hoặc `@ManyToMany` theo mapping phù hợp.

Ví dụ một playlist cần giữ thứ tự các item entity, và item có thể có ID/trạng thái riêng:

~~~java
@Entity
@Table(name = "playlists")
public class Playlist {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @OneToMany(
        cascade = CascadeType.ALL,
        orphanRemoval = true
    )
    @JoinTable(
        name = "playlist_entries",
        joinColumns = @JoinColumn(name = "playlist_id"),
        inverseJoinColumns = @JoinColumn(name = "entry_id")
    )
    @OrderColumn(name = "position_idx")
    private List<PlaylistEntry> entries = new ArrayList<>();

    protected Playlist() {
    }

    public void append(PlaylistEntry entry) {
        entries.add(entry);
    }

    public void move(int from, int to) {
        PlaylistEntry entry = entries.remove(from);
        entries.add(to, entry);
    }
}
~~~

Đoạn mapping này cần thêm class entity `PlaylistEntry` có `@Id` và các trường nghiệp vụ tương ứng. Dùng `@JoinTable` để minh họa **vị trí được lưu trong bảng liên kết** `playlist_entries`, không bắt buộc phải ở bảng entity item.

~~~text
playlists             playlist_entries                playlist_item
    id -----> playlist_id | position_idx | entry_id -----> id
                                  0
                                  1
                                  2
~~~

Vị trí lưu ở đâu phụ thuộc mapping collection:

| Mapping | Vị trí của order column thường nằm ở đâu? |
| --- | --- |
| `@ElementCollection List<String>` | Bảng collection table |
| `@OneToMany` dùng foreign key ở bảng child | Bảng child |
| `@OneToMany` dùng join table | Bảng join table |
| `@ManyToMany` có join table | Bảng join table |

Đối với quan hệ hai chiều `@OneToMany(mappedBy="...")`, cần hiểu thêm phía sở hữu FK và cách provider duy trì cột vị trí. `@OrderColumn` trên collection không có nghĩa child có một trường `position` được JPA quản lý như attribute thường. Cần xem mapping thực tế và đánh giá các ràng buộc `NOT NULL` / `UNIQUE` của cột vị trí.

### 8.1. Vì sao OneToMany unidirectional cần chú ý?

Trong mapping `@OneToMany @JoinColumn` một chiều với FK nằm ở bảng child, một số provider có thể INSERT child trước rồi UPDATE FK hoặc vị trí sau. Nếu `order_id` / `position_idx` có `NOT NULL` mà SQL trung gian chưa có giá trị, database có thể từ chối thao tác.

Cách khắc phục không phải tùy tiện vô hiệu ràng buộc. Nên xem lại:

- Có cần đặt `@ManyToOne` ở child làm owning side cho FK không?
- Có phù hợp dùng join table cho quan hệ một chiều không?
- Provider xử lý thứ tự INSERT/UPDATE và order column ra sao ở phiên bản đang chạy?
- Có thể thiết kế entity item với field `sortOrder` riêng được ứng dụng quản lý không?

Chỉ dùng một cấu hình mà ứng dụng hiểu rõ SQL và schema của nó.

## 9. Reorder, INSERT và DELETE: chi phí cập nhật vị trí

Giả sử một danh sách có 5 phần tử:

~~~text
Index  Item
0      A
1      B
2      C
3      D
4      E
~~~

**Append cuối danh sách** thường chỉ cần thêm một phần tử ở index 5:

~~~text
A B C D E F
0 1 2 3 4 5
~~~

**Chèn ở đầu**:

~~~text
X A B C D E
0 1 2 3 4 5
~~~

đòi hỏi các phần tử cũ tăng vị trí. Provider có thể phải thực hiện nhiều thao tác cập nhật hoặc xây dựng lại dữ liệu collection.

**Xóa giữa**:

~~~text
Trước: A B C D E     (0,1,2,3,4)
Xóa B: A C D E       (0,1,2,3)
~~~

những phần tử phía sau cần vị trí mới để giữ dãy liên tục theo cơ chế order column.

**Hoán đổi hai phần tử**:

~~~text
Trước:  A B C D
Sau:    A D C B
~~~

có thể tạo thay đổi index ở hai hoặc nhiều hàng.

Với `@OrderBy`, các thao tác kéo-thả trên List trong memory **không có một cột vị trí được provider lưu**. Nếu business yêu cầu sort theo `priority` và muốn đổi thứ tự, phải cập nhật chính `priority` hoặc thuộc tính sort khác, không chỉ đổi index List.

### 9.1. UNIQUE constraint có thể va chạm trong quá trình swap

Giả sử schema có:

~~~sql
UNIQUE (reading_list_id, position_idx)
~~~

Đổi vị trí 0 và 1 theo hai lệnh SQL đơn giản:

~~~sql
UPDATE reading_list_items
SET position_idx = 1
WHERE reading_list_id = 50 AND position_idx = 0;

UPDATE reading_list_items
SET position_idx = 0
WHERE reading_list_id = 50 AND position_idx = 1;
~~~

Lệnh đầu tiên có thể **vi phạm unique** vì vị trí 1 vẫn đang được phần tử cũ sử dụng. Đây chỉ là ví dụ về nguy cơ, không phải SQL mà JPA bắt buộc phát ra.

Các cách xử lý phụ thuộc provider và database: có thể phải sắp lại thao tác, dùng vị trí tạm, dùng ràng buộc có thể trì hoãn, hoặc lựa chọn chiến lược lưu thứ tự khác. Đừng giả định thêm `UNIQUE(owner_id, position)` sẽ luôn tương thích với mọi thuật toán reorder của ORM mà không thử trên hệ thống thực tế.

### 9.2. Không nhầm order column với @Version

Một entity parent có `@Version` có thể phát hiện một số dạng cập nhật đồng thời, nhưng **việc thay đổi collection có tăng version parent hay không** phụ thuộc mapping và provider. Nếu hai người đồng thời reorder cùng một List, có thể xảy ra mất cập nhật mà không được phát hiện chỉ bằng việc “có @Version ở đâu đó”.

Khi thứ tự là dữ liệu quan trọng, ứng dụng nên:

- Xác định transaction boundary cho reorder.
- Dùng kiểm soát phiên bản/khóa đồng thời phù hợp.
- Xử lý xung đột hoặc yêu cầu người dùng tải lại.
- Giữ ràng buộc DB để không lưu dữ liệu vị trí bị trùng.
- Tránh thao tác reorder dựa trên snapshot quá cũ mà không kiểm tra.

## 10. Thay @OrderColumn bằng trường sortOrder có hợp lý không?

Có. Một lựa chọn khác là **tự mô hình hóa vị trí thành thuộc tính entity**:

~~~java
@Entity
@Table(name = "playlist_items")
public class PlaylistItem {

    @Id
    private Long id;

    @Column(name = "sort_order", nullable = false)
    private int sortOrder;

    // playlist, title, getters/setters ...
}
~~~

Phía parent:

~~~java
@OneToMany(mappedBy = "playlist")
@OrderBy("sortOrder ASC, id ASC")
private List<PlaylistItem> items = new ArrayList<>();
~~~

Trong thiết kế này:

1. `sortOrder` là **trường nghiệp vụ thực sự** của entity.
2. Ứng dụng tự quyết định giá trị khi reorder.
3. `@OrderBy` chỉ đọc lại theo `sortOrder`.
4. JPA không tự điều chỉnh `sortOrder` theo vị trí hiện tại của List.

Lựa chọn này có thể phù hợp nếu cần API cập nhật vị trí tường minh, đặt khoảng trống giữa các giá trị sort, hoặc truy vấn item độc lập theo `sortOrder`. Đổi lại, ứng dụng phải tự quản lý tính liên tục, xử lý giá trị trùng, kiểm soát đồng thời và đồng bộ giữa Java collection với database.

| Mô hình | Ai quyết định vị trí? | Ai cập nhật cột vị trí? |
| --- | --- | --- |
| `@OrderColumn` | Thứ tự List | JPA provider |
| Trường `sortOrder` + `@OrderBy` | Logic ứng dụng | Ứng dụng qua thuộc tính entity/SQL |
| `@OrderBy("title ASC")` | Giá trị `title` | Không có cột vị trí riêng |

**Không ghép cùng lúc `@OrderColumn` do JPA sở hữu với một field `sortOrder` cũng ghi vào cùng cột** nếu chưa có thiết kế rõ cơ chế ghi; điều đó dễ gây duplicate column mapping hoặc kết quả không nhất quán.

## 11. Sắp xếp ở mapping khác với ORDER BY trong từng truy vấn

`@OrderBy` đặt trên collection giúp quy định **thứ tự mặc định khi truy xuất collection đó**. Nhưng có những màn hình cần thứ tự khác.

Ví dụ `Library.books` mặc định sắp theo tên:

~~~java
@OneToMany(mappedBy = "library")
@OrderBy("title ASC")
private List<Book> books;
~~~

Màn hình “Sách mới nhất” muốn sắp theo thời gian tạo:

~~~java
List<Book> latest = em.createQuery(
    """
    SELECT b
    FROM Book b
    WHERE b.library.id = :libraryId
    ORDER BY b.createdAt DESC, b.id DESC
    """,
    Book.class
)
.setParameter("libraryId", libraryId)
.getResultList();
~~~

Ví dụ JPQL giả định entity `Book` có thuộc tính được mapping `createdAt`. `ORDER BY` của truy vấn **không chỉnh sửa annotation `@OrderBy`** trên collection và không tạo vị trí lâu dài trong DB.

Các trường hợp query riêng thường phù hợp với:

- Phân trang danh sách dài.
- Lọc theo điều kiện tìm kiếm.
- Cho phép người dùng chọn cột sắp tăng/giảm.
- Chỉ lấy một vài trường bằng DTO projection.
- Cần order theo biểu thức/tổ hợp join phức tạp hơn biểu thức mapping đơn giản.

Không nên buộc tải toàn bộ collection chỉ để sort và phân trang một số lượng lớn phần tử. Có thể query từ entity phần tử với `WHERE` và `ORDER BY`, rồi phân trang ở database.

### 11.1. Đường dẫn @OrderBy theo tên Java

`@OrderBy("title ASC")` tham chiếu `Book.title`. Nếu cột SQL là `book_title`, vẫn dùng tên Java `title`.

Ví dụ:

~~~java
@Column(name = "book_title")
private String title;

// Đúng:
@OrderBy("title ASC")

// Không đúng theo tên thuộc tính Java nếu class không có book_title:
// @OrderBy("book_title ASC")
~~~

Với những cấu trúc embeddable, đường dẫn thuộc tính lồng có thể được hỗ trợ theo quy tắc của đặc tả; phải dùng **tên thuộc tính Java có mapping hợp lệ**, không viết tùy ý biểu thức SQL/dialect vào `@OrderBy` của JPA rồi coi nó portable.

## 12. NULL, trùng giá trị và thứ tự ổn định

Khi sắp theo trường `title`, `priority` hay `createdAt`, có những dữ liệu gây bất định:

1. **Trùng khóa sort**: hai Book cùng title.
2. **Giá trị NULL**: không có ngày xuất bản.
3. **Quy tắc collation**: phân biệt chữ hoa/chữ thường, dấu tiếng Việt.
4. **Thứ tự nhiều tiêu chí**: title giống nhau nhưng ID khác.

Với `@OrderBy`:

~~~java
@OrderBy("title ASC, id ASC")
~~~

thêm `id` giúp phân biệt tie trong cùng một entity type. Nhưng thứ tự giữa NULL và giá trị không NULL, cách so sánh string và collation còn phụ thuộc DB/dialect; cần kiểm soát schema, query riêng hoặc dữ liệu chuẩn hóa nếu yêu cầu sản phẩm rất cụ thể.

Với `@OrderColumn`, thứ tự không phụ thuộc vào tên, ngày hay collation. Nhưng nó lại phụ thuộc **tính đúng đắn của giá trị index được lưu và duy trì**. Nếu dữ liệu bị chỉnh sửa trực tiếp ở DB làm mất vị trí hoặc trùng index, việc materialize List có thể gây lỗi hoặc thứ tự bất thường tùy provider.

### 12.1. Dữ liệu trùng nhau trong List<String>

Giả sử danh sách người dùng cố ý chứa hai lần `"Read"`:

~~~text
[0] Read
[1] Practice
[2] Read
~~~

`@OrderColumn` phân biệt hai lần xuất hiện bằng vị trí. Đây là một điểm khác với các cấu trúc set-based và một lý do `List` cùng index lưu trữ phù hợp cho checklist/bước thực hiện có thể lặp tên.

Với `@OrderBy` trên các giá trị `"Read"` trùng nhau, chỉ có một tiêu chí bằng nhau; nếu không có tiêu chí khác phân biệt hai phần tử, ứng dụng không thể dựa vào sort theo value để bảo toàn danh tính từng vị trí.

## 13. Những ngộ nhận thường gặp

| Nhận định | Thực tế |
| --- | --- |
| “List Java đã có index nên JPA luôn lưu index.” | Không. Cần mapping phù hợp như `@OrderColumn` nếu thứ tự phải được persist. |
| “@OrderBy tạo cột position.” | Không. Nó chỉ nêu tiêu chí sắp từ giá trị đã lưu. |
| “@OrderColumn chỉ là SQL ORDER BY.” | Không. Nó lưu và duy trì cột vị trí khi collection List thay đổi. |
| “Đổi chỗ hai phần tử trong @OrderBy là đủ để lưu reorder.” | Không. Không có cột index được ghi lại chỉ nhờ swap trong memory. |
| “Đổi title của item có @OrderColumn sẽ tự chuyển nó lên đầu.” | Không. Vị trí được lưu độc lập với title. |
| “Mọi @OrderBy tự sắp lại List ngay sau setter.” | Không thể giả định; thường thứ tự được áp dụng khi tải collection. |
| “@OrderColumn tốt cho Map vì Map cũng có key.” | Không. Map key là dữ liệu nhận diện entry, không phải vị trí theo index. |
| “@MapKeyColumn cũng là order column.” | Không. Nó dùng để ánh xạ key của Map. |
| “JPA luôn UPDATE đúng một hàng khi kéo thả.” | Không. Reorder có thể ảnh hưởng nhiều index hoặc ghi lại collection. |
| “Có UNIQUE(owner, position) thì mọi hoán đổi đều tự hợp lệ.” | Có thể va chạm constraint ở các bước SQL trung gian. |
| “@OrderBy tự đảm bảo phân trang ổn định.” | Muốn phân trang ổn định cần thứ tự đủ phân biệt và query phù hợp. |
| “Có @Version trên parent thì mọi thay đổi thứ tự đều phát hiện xung đột.” | Phải xét mapping/provider và chiến lược đồng thời thực tế. |

## 14. Lỗi và cách chẩn đoán

### 14.1. Sau khi reload, thứ tự bị mất

**Triệu chứng:** trong cùng request, `Collections.swap(list, 0, 1)` hiển thị đúng; mở lại trang, thứ tự quay về cũ.

Nguyên nhân có thể là collection chỉ có `@OrderBy` theo thuộc tính, hoặc không có annotation giữ vị trí. Đổi sang `@OrderColumn` khi thứ tự thực sự là dữ liệu độc lập, hoặc thiết kế trường `sortOrder` và ghi vị trí qua service.

### 14.2. Có @OrderColumn nhưng thấy nhiều UPDATE

**Triệu chứng:** đổi vị trí một item khiến ORM phát nhiều câu `UPDATE` hoặc `DELETE/INSERT`.

Điều này có thể đúng với cách duy trì dãy index của List. Cần xem độ lớn danh sách, vị trí chèn/xóa và kiểu mapping (`@ElementCollection`, `@OneToMany`, join table). Nếu list rất dài và reorder liên tục, cân nhắc mô hình `sortOrder` độc lập, fractional ranking hoặc API reorder batch được thiết kế rõ.

### 14.3. Vi phạm UNIQUE khi đổi chỗ hai item

Nếu bảng có `UNIQUE(list_id, position_idx)`, xem trình tự SQL thực tế tại flush, các giá trị tạm và đặc điểm constraint DB. Không tắt uniqueness vội chỉ để bỏ lỗi; cần phối hợp mapping và thuật toán reorder để giữ tính toàn vẹn.

### 14.4. @OrderBy dùng sai tên cột

~~~java
@Column(name = "created_at")
private Instant createdAt;

@OrderBy("created_at DESC") // Sai tên thuộc tính trong entity Java.
private List<Event> events;
~~~

Sử dụng tên Java:

~~~java
@OrderBy("createdAt DESC")
private List<Event> events;
~~~

### 14.5. Hiệu năng đọc chậm do sort

Truy vấn collection có `ORDER BY` theo cột không có index hoặc lọc nhiều hàng có thể cần sort tốn chi phí. Đánh giá query plan và index phù hợp, ví dụ cho collection Book:

~~~sql
CREATE INDEX idx_books_library_title_id
    ON books (library_id, title, id);
~~~

Đây là ví dụ index theo điều kiện `library_id = ?` rồi sort `title, id`. Hiệu quả thực tế phụ thuộc distribution, collation, DB optimizer, số bản ghi và cách provider viết SQL.

### 14.6. Không rõ ai sở hữu cột vị trí

Với mapping one-to-many hai chiều, cần xác định:

- `@ManyToOne` nào đang sở hữu FK?
- `@OrderColumn` đặt trên List nào?
- Order column nằm trong child table hay join table?
- Provider sẽ phát SQL cập nhật FK và position như thế nào?
- Có ràng buộc `nullable=false` hoặc `unique` nào ngăn các bước trung gian không?

Không kết luận từ Java collection riêng lẻ; hãy nhìn mapping, schema và hành vi provider đang chạy.

## 15. Chọn annotation theo tình huống

### Tình huống A — Danh sách bài viết mới nhất

Yêu cầu luôn hiển thị các bài viết mới trước, không cho người dùng kéo thả.

~~~java
@OneToMany(mappedBy = "author")
@OrderBy("publishedAt DESC, id DESC")
private List<Article> articles;
~~~

**Chọn `@OrderBy`** vì thứ tự phụ thuộc `publishedAt`. Với dữ liệu rất lớn, có thể query phân trang riêng thay vì tải toàn bộ collection.

### Tình huống B — Playlist do người dùng sắp xếp

Người dùng tự chọn thứ tự phát; đổi tên bài hát không được tự đổi vị trí.

~~~java
@OneToMany(cascade = CascadeType.ALL, orphanRemoval = true)
@JoinTable(
    name = "playlist_entries",
    joinColumns = @JoinColumn(name = "playlist_id"),
    inverseJoinColumns = @JoinColumn(name = "entry_id")
)
@OrderColumn(name = "position_idx")
private List<PlaylistEntry> entries;
~~~

**Chọn `@OrderColumn`** nếu provider và schema phù hợp vì cần lưu thứ tự List độc lập với thuộc tính item.

### Tình huống C — Bộ tag của bài viết

Mỗi tag chỉ xuất hiện một lần; ứng dụng chủ yếu kiểm tra membership, không quan tâm vị trí người dùng.

~~~java
@ManyToMany
private Set<Tag> tags;
~~~

**Không cần `@OrderColumn`**. Nếu màn hình cần tags theo tên, có thể dùng query riêng có `ORDER BY` hoặc một mapping `@OrderBy("name ASC")` phù hợp.

### Tình huống D — Bảng từ điển theo mã ngôn ngữ

Cần truy xuất giá trị bằng `localeCode`, không cần thứ tự phần tử lưu trữ.

~~~java
@ElementCollection
@MapKeyColumn(name = "locale_code")
@Column(name = "display_name")
private Map<String, String> translations;
~~~

**Chọn Map với key mapping**, không dùng `@OrderColumn`. Nếu giao diện phải sắp key tăng dần, sắp ở tầng truy vấn hoặc ứng dụng.

### Tình huống E — Danh sách bước quy trình có vị trí điều chỉnh tự do

Một quy trình có các bước “kiểm tra”, “phê duyệt”, “gửi email”; người dùng có thể di chuyển bước và giữ thứ tự qua nhiều phiên.

Nếu bước chỉ là text, `@ElementCollection List<String>` + `@OrderColumn` có thể đủ. Nếu mỗi bước có ID, trạng thái, người phụ trách và lịch sử, nên dùng entity `WorkflowStep` rồi lưu vị trí bằng `@OrderColumn` hoặc trường `sortOrder` rõ ràng.

### Tình huống F — Danh sách ưu tiên có hệ số nghiệp vụ

Yêu cầu: các task ưu tiên cao hiển thị trước và task cùng ưu tiên sắp theo thời gian tạo. Đây là thứ tự **tính từ các field**, không phải kéo-thả tự do.

~~~java
@OneToMany(mappedBy = "project")
@OrderBy("priority DESC, createdAt ASC, id ASC")
private List<Task> tasks;
~~~

**Chọn `@OrderBy`**. Nếu người dùng cần kéo-thả mà vẫn giữ nhóm ưu tiên, cần xác định business rule mới: lưu thêm vị trí trong từng nhóm hoặc một field ranking có cấu trúc.

## 16. Bài tập thực hành có lời giải

### Bài 1. Chọn annotation

Một hệ thống quản lý khóa học hiển thị bài học theo `publishedAt DESC`. Giảng viên không thể thay đổi thứ tự ngoài việc chỉnh ngày công bố.

**Đáp án:** `@OrderBy("publishedAt DESC, id DESC")` trên collection hoặc `ORDER BY` trong query. Không cần lưu một cột index để mô tả thứ tự do ngày công bố quyết định.

### Bài 2. Phát hiện sai lầm khi kéo-thả

~~~java
@OneToMany(mappedBy = "playlist")
@OrderBy("title ASC")
private List<Track> tracks;
~~~

UI gọi:

~~~java
Collections.swap(playlist.getTracks(), 0, 1);
~~~

Sau khi reload, hai bài hát lại sắp theo title. Có phải lỗi ORM?

**Đáp án:** Không nhất thiết. Mapping chỉ quy định thứ tự tải theo title; nó không lưu thứ tự List tùy chỉnh. Muốn lưu kéo-thả, cần order column hoặc một trường vị trí có quản lý cập nhật.

### Bài 3. Đọc schema cho @OrderColumn

~~~text
reading_list_id | position_idx | book_title
              8 |            0 | A
              8 |            1 | C
              8 |            2 | B
~~~

Khi tải List, thứ tự mong muốn là gì?

**Đáp án:** `[A, C, B]`. Position 0 đứng đầu, 1 tiếp theo, rồi 2. Tên sách không làm thay đổi thứ tự vì List đang được tái tạo từ `position_idx`.

### Bài 4. Thêm phần tử vào vị trí đầu

Ban đầu List có 200 phần tử và sử dụng `@OrderColumn`. Thêm một phần tử vào index 0 có thể chỉ cần một INSERT không?

**Đáp án:** Không được bảo đảm. Các phần tử cũ có thể phải dịch index, làm phát sinh nhiều thao tác cập nhật hoặc xây dựng lại collection. Cần đánh giá write amplification khi list dài và reorder thường xuyên.

### Bài 5. Map có sắp index như List không?

Entity chứa:

~~~java
@ElementCollection
@MapKeyColumn(name = "locale_code")
private Map<String, String> labels;
~~~

Một lập trình viên muốn đặt `@OrderColumn` để Map hiển thị theo locale.

**Đáp án:** Không phù hợp. `locale_code` là map key, không phải vị trí trong List. Để duyệt theo key, cần chọn một cách sắp xếp phù hợp ở query hoặc tầng Java; không dùng order column như index của Map.

### Bài 6. Ưu tiên sắp xếp khác nhau

Dữ liệu:

~~~text
Task A: priority = 3, createdAt = 2026-11-10
Task B: priority = 5, createdAt = 2026-11-12
Task C: priority = 3, createdAt = 2026-11-09
~~~

Dùng:

~~~java
@OrderBy("priority DESC, createdAt ASC")
~~~

Thứ tự nào?

**Đáp án:** B (priority 5), rồi C (priority 3 và createdAt sớm hơn), rồi A. Đây là thứ tự **suy ra từ giá trị trường**, không có cột position.

### Bài 7. Có cần UNIQUE(owner, position)?

Với `@OrderColumn`, hai item cùng position 1 trong cùng list có hợp lý không?

**Đáp án:** Về mô hình danh sách vị trí liên tiếp, không: một vị trí tương ứng một phần tử. Ràng buộc unique phù hợp để bảo vệ dữ liệu cuối cùng, nhưng cần đảm bảo thuật toán cập nhật/reorder của provider không xung đột với unique ở bước trung gian.

### Bài 8. Khi nào dùng sortOrder + @OrderBy?

Hệ thống muốn giữ field `sortOrder` trong API, cho phép client gửi lệnh cập nhật vị trí tường minh; đồng thời cần query theo thứ tự đó ngoài collection.

**Đáp án:** Có thể dùng field `sortOrder` do service quản lý và `@OrderBy("sortOrder ASC, id ASC")` để tải. Đây là thiết kế thay thế `@OrderColumn`, với trách nhiệm duy trì thứ tự chuyển sang ứng dụng.

## 17. Ghi nhớ theo ba câu hỏi

Khi gặp một collection trong mô hình JPA, hãy phân biệt ba điều:

1. **Dựa vào giá trị nào để sắp?** Nếu là `title`, `createdAt`, `priority`, chọn `@OrderBy` hoặc query `ORDER BY`.
2. **Có cần ghi nhớ chính vị trí 0, 1, 2… sau khi người dùng kéo-thả không?** Nếu có và dùng `List`, cân nhắc `@OrderColumn` hoặc trường vị trí riêng.
3. **Collection là List, Set hay Map?** `List` có index, `Set` quản lý membership, `Map` truy xuất theo key. Không áp dụng cơ chế lưu vị trí của List cho Map hoặc Set.

Tóm lại:

- **`@OrderBy` = sắp theo thuộc tính khi đọc**; không tự lưu vị trí.
- **`@OrderColumn` = lưu thứ tự List bằng cột index**; có thể làm phát sinh thêm SQL khi chèn, xóa, đổi chỗ.
- **`@MapKeyColumn` = lưu key của Map**, hoàn toàn khác cột index của List.
- **Trường `sortOrder` + `@OrderBy`** là một lựa chọn thiết kế khác khi ứng dụng muốn kiểm soát vị trí như dữ liệu nghiệp vụ.

Chọn annotation theo **ngữ nghĩa thứ tự cần bảo toàn**, rồi đối chiếu với schema, transaction, khối lượng cập nhật và các ràng buộc database. Một danh sách “có thứ tự” trên giao diện chưa đủ để kết luận hệ thống cần `@OrderColumn`; điều quyết định là **thứ tự được tính từ nội dung hay phải được lưu như một trạng thái riêng**.
