# List, Set, Map và bag khác nhau về ngữ nghĩa ánh xạ

Trong Java, `List`, `Set` và `Map` đều là những cấu trúc lưu nhiều phần tử, nhưng **cách chúng biểu diễn thứ tự, phần tử trùng và khóa tra cứu rất khác nhau**. Khi ánh xạ các tập hợp này sang cơ sở dữ liệu quan hệ bằng JPA/Hibernate, sự khác biệt còn ảnh hưởng đến cấu trúc bảng, câu lệnh SQL, khả năng lưu lại thứ tự sau khi tải lại và chi phí cập nhật.

Hibernate còn có khái niệm **bag**: tập hợp cho phép phần tử trùng, **không có chỉ số vị trí được lưu trong database**. Bag đặc biệt dễ gây nhầm lẫn vì trong Java nó có thể được khai báo bằng `Collection<T>` hoặc một `List<T>` không có ánh xạ chỉ số; chỉ nhìn kiểu `List` trong mã Java chưa đủ để kết luận Hibernate đang lưu một danh sách có thứ tự bền vững.

Bài học thuộc chương **Giá trị và tập hợp** của module *Data Persistence Relational Access ORM Hibernate*. Ví dụ sử dụng Jakarta Persistence (`jakarta.persistence.*`) và Hibernate ORM. Cú pháp SQL minh họa dùng PostgreSQL; tên cột và cách Hibernate thực thi SQL có thể khác tùy phiên bản, chiến lược ánh xạ và hệ quản trị.

## 1. Ba câu hỏi quyết định ngữ nghĩa một collection

Trước khi thêm một collection vào entity, hãy trả lời:

1. **Có cho phép giá trị trùng không?** Hai phần tử bằng nhau theo `equals()` có được xuất hiện cùng lúc không?
2. **Thứ tự có ý nghĩa nghiệp vụ không?** Nếu kéo phần tử từ vị trí thứ ba lên đầu, thứ tự mới có phải được lưu sau khi đóng và mở lại ứng dụng không?
3. **Có cần một khóa tra cứu riêng cho mỗi giá trị không?** Người dùng muốn gọi `translations.get("vi")` hay chỉ duyệt danh sách các bản dịch?

Một cách nhìn tổng quát:

| Kiểu/ngữ nghĩa | Phần tử trùng | Thứ tự theo vị trí được lưu | Khóa tra cứu | Dùng khi |
| --- | --- | --- | --- | --- |
| `List` có `@OrderColumn` | Có | **Có**; database có cột vị trí | Chỉ số `0, 1, 2, ...` | Các chương sách, bước quy trình, ảnh có vị trí kéo thả |
| `Set` | Không trong tập hợp Java, dựa vào `equals/hashCode` | Không mặc định | Chính giá trị/phần tử | Tập thẻ, quyền, nhãn không lặp |
| `Map<K,V>` | Giá trị `V` có thể trùng, **khóa `K` phải phân biệt theo Map** | Không mặc định | `K` | Bản dịch theo ngôn ngữ, thông số theo tên thuộc tính |
| **Bag** | Có | **Không** | Không có khóa/chỉ số được lưu cho từng lần xuất hiện | Nhiều giá trị lặp mà thứ tự không quan trọng |

**Giá trị “trùng” ở cấp Java và ràng buộc duy nhất của SQL là hai chuyện khác nhau.** `Set` ngăn phần tử bằng nhau trong bộ nhớ, còn database chỉ thực sự ngăn dòng trùng nếu schema có khóa hoặc ràng buộc phù hợp. Ngược lại, một bag có thể cho phép hai giá trị bằng nhau nhưng bảng SQL do ứng dụng thiết kế có ràng buộc khiến việc lưu hai dòng giống nhau không thể thực hiện.

## 2. Kiểu Java không đồng nghĩa hoàn toàn với cách lưu ở database

Xét ba câu lệnh:

~~~java
List<String> chapters = new ArrayList<>();
Set<String> keywords = new HashSet<>();
Map<String, String> titlesByLanguage = new HashMap<>();
~~~

Trong **bộ nhớ Java**:

- `List` cho phép phần tử lặp, có chỉ số và bảo toàn trình tự các phần tử của chính đối tượng list.
- `Set` không giữ các phần tử mà `equals()` xem là bằng nhau. `HashSet` không cam kết thứ tự lặp.
- `Map` ánh xạ mỗi key tới một value. `put` một key đã có sẽ thay value cũ; `HashMap` không cam kết thứ tự các entry.

Nhưng một database quan hệ **không tự có khái niệm danh sách theo chỉ số**. Nếu lưu:

| book_id | heading |
| ---: | --- |
| 7 | Giới thiệu |
| 7 | Cấu hình |
| 7 | Truy vấn |

thì không thể kết luận hàng “Giới thiệu” sẽ luôn được đọc trước “Cấu hình”. **Không có `ORDER BY` thì SQL không bảo đảm thứ tự kết quả**, kể cả khi một lần chạy tình cờ trả về theo thứ tự chèn.

Để lưu thứ tự độc lập với thứ tự vật lý của các hàng, cần thêm metadata, ví dụ cột vị trí:

| book_id | chapter_position | heading |
| ---: | ---: | --- |
| 7 | 0 | Giới thiệu |
| 7 | 1 | Cấu hình |
| 7 | 2 | Truy vấn |

Với `Map`, database cần biểu diễn key, ví dụ:

| book_id | language_code | title |
| ---: | --- | --- |
| 7 | vi | Hibernate cơ bản |
| 7 | en | Hibernate Basics |

Với `Set` hoặc bag, các hàng thường được lưu trong bảng collection nhưng ý nghĩa duy nhất hay trùng lặp phải được xem từ mapping **và** ràng buộc dữ liệu.

## 3. `@ElementCollection`: nền tảng cho tập hợp giá trị

JPA sử dụng `@ElementCollection` khi một entity sở hữu nhiều **giá trị cơ bản** (ví dụ `String`, `Integer`) hoặc nhiều đối tượng `@Embeddable`. Các phần tử này không phải entity độc lập có `@Id` và không có vòng đời persistence riêng như `@OneToMany`.

Ví dụ một cuốn sách có nhiều nhãn:

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
import jakarta.persistence.Table;
import java.util.HashSet;
import java.util.Set;

@Entity
@Table(name = "books")
public class Book {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 200)
    private String title;

    @ElementCollection
    @CollectionTable(
        name = "book_keywords",
        joinColumns = @JoinColumn(name = "book_id")
    )
    @Column(name = "keyword", nullable = false, length = 50)
    private Set<String> keywords = new HashSet<>();

    protected Book() {
    }

    public Book(String title) {
        this.title = title;
    }

    public void addKeyword(String keyword) {
        keywords.add(keyword);
    }
}
~~~

Các hàng của bảng `book_keywords` liên kết với `books` bằng khóa ngoại `book_id`:

~~~text
books                     book_keywords
+----+----------------+   +---------+------------+
| id | title          |   | book_id | keyword    |
+----+----------------+   +---------+------------+
|  7 | Hibernate      |<--|    7    | jpa        |
+----+----------------+   |    7    | persistence|
                         +---------+------------+
~~~

`@CollectionTable` xác định bảng chứa các phần tử của tập hợp, còn `@Column` xác định cột chứa **giá trị phần tử**. Nếu muốn lưu một collection entity, cần xem `@OneToMany` hoặc `@ManyToMany`, vì `@ElementCollection` dành cho giá trị.

Các ví dụ tiếp theo sử dụng các entity độc lập tên `ChapteredBook`, `TaggedBook`, `NotedBook` và `LocalizedBook` để dễ phân biệt các phương án. Trong ứng dụng thật, một entity có thể sở hữu nhiều collection; phần lưu ý cuối bài sẽ giải thích chi phí khi nạp nhiều collection cùng lúc.

## 4. `List` có thứ tự lưu trữ: `@OrderColumn`

Giả sử sách hướng dẫn có các chương mà người biên tập có thể **kéo thả để thay thứ tự**. Trật tự là một phần của dữ liệu nghiệp vụ, nên cần một cột vị trí.

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
@Table(name = "chaptered_books")
public class ChapteredBook {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 200)
    private String title;

    @ElementCollection
    @CollectionTable(
        name = "book_chapters",
        joinColumns = @JoinColumn(name = "book_id")
    )
    @OrderColumn(name = "chapter_position")
    @Column(name = "heading", nullable = false, length = 200)
    private List<String> chapterHeadings = new ArrayList<>();

    protected ChapteredBook() {
    }

    public ChapteredBook(String title) {
        this.title = title;
    }

    public void appendChapter(String heading) {
        chapterHeadings.add(heading);
    }

    public void moveChapter(int from, int to) {
        if (from == to) {
            return;
        }
        String heading = chapterHeadings.remove(from);
        chapterHeadings.add(to, heading);
    }

    public List<String> getChapterHeadings() {
        return List.copyOf(chapterHeadings);
    }
}
~~~

`@OrderColumn(name = "chapter_position")` bảo Hibernate duy trì **chỉ số của mỗi phần tử** trong bảng collection. Với ngữ nghĩa list theo JPA, giá trị vị trí bắt đầu từ **0** và các vị trí biểu diễn trình tự liên tục của danh sách. Cột `chapter_position` do provider quản lý; mã nghiệp vụ thao tác trên `List`.

Ví dụ ban đầu:

~~~text
Java List<String>                      Bảng book_chapters
[0] "Giới thiệu"                -->       book_id=7, position=0, heading="Giới thiệu"
[1] "Cấu hình"                   -->       book_id=7, position=1, heading="Cấu hình"
[2] "Truy vấn"                   -->       book_id=7, position=2, heading="Truy vấn"
~~~

Khi gọi `moveChapter(2, 0)`:

~~~text
[0] "Truy vấn"
[1] "Giới thiệu"
[2] "Cấu hình"
~~~

Khi collection managed được đồng bộ, Hibernate phải cập nhật cách lưu vị trí để sau khi tải lại vẫn có thứ tự này. Tùy mapping và phiên bản, ORM có thể sinh nhiều `UPDATE`/`DELETE`/`INSERT`; không nên giả định một lệnh Java `list.add(0, item)` tương đương một câu SQL duy nhất.

### Vì sao `@OrderColumn` là ánh xạ `List` theo nghĩa vị trí?

Với `@OrderColumn`, thứ tự được lưu như dữ liệu có thể thay đổi. Sau khi đóng `EntityManager`, mở context mới và nạp lại, Hibernate có thể sắp phần tử theo cột vị trí để tái tạo trình tự.

Nhờ vậy:

- Hai chương có cùng tiêu đề vẫn có thể xuất hiện ở **hai vị trí khác nhau**.
- Di chuyển chương thay đổi thứ tự của list, ngay cả khi nội dung `heading` không đổi.
- Chèn vào đầu danh sách có thể cần dịch chuyển vị trí của nhiều hàng.
- Vị trí không nên được mã nghiệp vụ tự sửa bằng SQL khi Hibernate vẫn quản lý collection trong context cũ.

**Chi phí đổi vị trí tăng theo số phần tử phải dịch chuyển.** Nếu một list chứa hàng chục nghìn phần tử và liên tục chèn giữa, cần đánh giá xem cột index liên tục có phù hợp hay nên thiết kế “số thứ tự” nghiệp vụ riêng có khoảng trống, chiến lược cấp lại thứ tự hoặc entity con có trường vị trí được quản lý rõ ràng.

### Lưu ý khi đặt ràng buộc duy nhất lên cột vị trí

Về mặt dữ liệu sau khi commit, một bộ `(book_id, chapter_position)` nên chỉ đến một vị trí trong danh sách. Tuy nhiên, nếu tự tạo `UNIQUE(book_id, chapter_position)` quá chặt và ORM đổi chỗ nhiều hàng bằng những `UPDATE` riêng, có thể phát sinh **xung đột unique tạm thời trong lúc reorder** tùy SQL Hibernate sinh và khả năng trì hoãn ràng buộc của database.

Vì vậy phải xem cách provider cập nhật collection và chiến lược schema trước khi thêm index/constraint. Chỉ nhìn trạng thái cuối cùng có vị trí duy nhất là chưa đủ để suy luận mọi chuỗi `UPDATE` đều thực thi được dưới một ràng buộc unique tức thời.

## 5. `List` không có `@OrderColumn` có thể mang ngữ nghĩa bag

Đây là khác biệt quan trọng nhất đối với Hibernate.

~~~java
@ElementCollection
@CollectionTable(
    name = "book_chapters",
    joinColumns = @JoinColumn(name = "book_id")
)
@Column(name = "heading")
private List<String> chapterHeadings = new ArrayList<>();
~~~

Kiểu phía Java vẫn là `List<String>`; tại thời điểm thao tác trong bộ nhớ, bạn vẫn có thể gọi `get(0)`, `add(0, ...)` hoặc `Collections.swap(...)`. Nhưng **mapping không có cột vị trí**. Nếu Hibernate diễn giải mapping này theo **bag semantics**, database chỉ biết những lần xuất hiện của từng giá trị, không biết chúng đứng đầu hay cuối.

Vì vậy:

~~~java
chapterHeadings.add("A");
chapterHeadings.add("B");
chapterHeadings.add("A");
~~~

có thể biểu diễn ba lần xuất hiện trong bảng SQL, gồm hai hàng có `heading='A'`, nhưng không có cơ sở để đảm bảo chúng sẽ trở về dưới thứ tự `A, B, A` sau khi đóng và nạp lại context.

Tùy phiên bản Hibernate và cách khởi tạo metadata, **`List` không có `@OrderColumn` có thể được ánh xạ theo bag semantics**; trên các phiên bản Hibernate 6 có cấu hình `hibernate.mapping.default_list_semantics`, lựa chọn mặc định/được cấu hình còn có thể ảnh hưởng trường hợp này. Để code không phụ thuộc ngầm vào mặc định, khi thứ tự thực sự quan trọng hãy **khai báo ánh xạ chỉ số rõ ràng bằng `@OrderColumn`**.

Cũng cần phân biệt Java `ArrayList` với persistent collection wrapper mà Hibernate cung cấp. Khi entity được quản lý, Hibernate có thể thay instance collection hoặc bọc nó để theo dõi thay đổi. Không nên ép kiểu field collection thành `ArrayList` hoặc dựa vào danh tính instance ban đầu.

## 6. `@OrderBy` sắp xếp khi đọc, không lưu chỉ số list

Một collection có thể muốn **đọc kết quả theo một thuộc tính** mà không cần lưu người dùng kéo thả thứ tự.

Giả sử entity `BookReview` có `createdAt`. Muốn xem các đánh giá mới nhất trước:

~~~java
@OneToMany(mappedBy = "book")
@OrderBy("createdAt DESC")
private List<BookReview> reviews = new ArrayList<>();
~~~

Đây là `jakarta.persistence.OrderBy`. Provider sử dụng biểu thức sắp xếp khi tải collection, thường tương ứng với `ORDER BY` trong SQL.

So sánh hai annotation:

| Đặc điểm | `@OrderColumn` | `@OrderBy` |
| --- | --- | --- |
| Cơ sở tạo thứ tự | **Chỉ số** được ORM lưu trong cột vị trí | Giá trị trường/biểu thức của phần tử |
| Cần cột chỉ số riêng | Có | Không |
| Kéo một phần tử sang vị trí khác rồi lưu | Có ngữ nghĩa lưu vị trí | Không tự động thay đổi giá trị dùng để sort |
| Sắp theo `createdAt DESC` | Không tự biểu diễn tiêu chí này | Phù hợp |
| Cùng tiêu chí sort | Vị trí vẫn xác định thứ tự | Các phần tử bằng tiêu chí có thể cần tiêu chí phụ để ổn định |
| Hành vi sau tải lại | Theo chỉ số đã lưu | Theo dữ liệu và quy tắc sort |

Nếu dùng:

~~~java
@OrderBy("createdAt DESC, id DESC")
~~~

thì tiêu chí phụ `id` giúp phân định các bản ghi có cùng thời điểm, miễn là các trường dùng trong order phù hợp và có giá trị. Đây vẫn là **thứ tự tính từ nội dung**, không phải chỉ số kéo thả.

Ví dụ:

~~~java
reviews.add(0, someOldReview);
~~~

thay đổi cấu trúc list ở Java tại thời điểm đó, nhưng nếu chỉ có `@OrderBy("createdAt DESC")`, Hibernate không tự thay `createdAt` để khiến phần tử cũ luôn đứng đầu sau lần tải mới.

`@OrderBy` có thể được dùng với nhiều collection type, nhưng **không biến một bag thành indexed list**. Trường hợp một `Set` được load theo truy vấn sắp xếp cũng không nên khiến ta mặc định mọi loại `Set` (đặc biệt `HashSet`) có thứ tự lặp bền vững.

### Thứ tự trong collection và `ORDER BY` ở truy vấn ngoài

Khi dùng JPQL:

~~~java
select b from ChapteredBook b order by b.title
~~~

`order by b.title` chỉ sắp xếp **danh sách entity `ChapteredBook` của kết quả query**, không tự định nghĩa lại thứ tự các phần tử `chapterHeadings` bên trong mỗi sách.

Đây là hai tầng khác nhau: thứ tự các hàng entity được trả về, và thứ tự của **một collection attribute** thuộc từng entity.

## 7. Bag: cho phép trùng, không lưu vị trí

Một **bag** là *multiset*: mỗi giá trị có thể xuất hiện nhiều lần, nhưng thứ tự của các lần xuất hiện không phải thành phần của mô hình dữ liệu.

Ví dụ lưu danh sách ghi chú dạng giá trị đơn giản, có thể trùng nội dung và không cần thứ tự:

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
import jakarta.persistence.Table;
import java.util.ArrayList;
import java.util.Collection;

@Entity
@Table(name = "noted_books")
public class NotedBook {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ElementCollection
    @CollectionTable(
        name = "book_notes",
        joinColumns = @JoinColumn(name = "book_id")
    )
    @Column(name = "note_text", length = 500)
    private Collection<String> notes = new ArrayList<>();

    protected NotedBook() {
    }

    public void addNote(String note) {
        notes.add(note);
    }
}
~~~

Với Hibernate, `Collection<String>` ở đây là cách tự nhiên để thể hiện **bag**. Ví dụ:

~~~java
book.addNote("Cần kiểm tra");
book.addNote("Đã sửa");
book.addNote("Cần kiểm tra");
~~~

Về mặt logic, bag có:

~~~text
"Cần kiểm tra"  -> 2 lần xuất hiện
"Đã sửa"        -> 1 lần xuất hiện
~~~

Database có thể lưu ba hàng:

| book_id | note_text |
| ---: | --- |
| 7 | Cần kiểm tra |
| 7 | Đã sửa |
| 7 | Cần kiểm tra |

Không có cột vị trí nên không thể yêu cầu ORM khôi phục chắc chắn trình tự `Cần kiểm tra → Đã sửa → Cần kiểm tra`. Nếu thứ tự là yêu cầu nghiệp vụ, nên đổi mô hình.

### Vì sao bag dễ tốn SQL khi cập nhật?

Với hai hàng trùng hệt nhau trong bảng collection, nếu không có khóa hàng riêng hoặc vị trí, ORM có thể khó xác định **chính xác hàng vật lý nào** cần xóa để bỏ đi một lần xuất hiện. Vì vậy một số mapping bag có thể khiến Hibernate **xóa những hàng collection của một owner rồi chèn lại phần còn lại** khi chỉnh sửa, tùy loại collection table và khả năng nhận diện dòng.

Minh họa một cách thực thi có thể xảy ra:

~~~sql
DELETE FROM book_notes WHERE book_id = 7;

INSERT INTO book_notes (book_id, note_text)
VALUES (7, 'Cần kiểm tra');

INSERT INTO book_notes (book_id, note_text)
VALUES (7, 'Đã sửa');
~~~

Đây **không phải SQL bắt buộc của mọi bag**. Hibernate có thể dùng lệnh khác theo mapping và phiên bản. Điều cần nhớ là **bag không có khóa vị trí cố định**, vì vậy thao tác xóa/sửa một lần xuất hiện có thể khó tối ưu hơn các collection có khóa dòng rõ ràng.

### Bag không phải một interface riêng trong Java Collections

Java chuẩn không có interface `Bag` bên cạnh `List` và `Set`. Hibernate diễn giải ngữ nghĩa collection dựa trên kiểu Java và metadata. Một `List` được ánh xạ theo bag vẫn có các phương thức Java của `List` khi đang dùng trong bộ nhớ, nhưng **không có hợp đồng lưu thứ tự giữa các phiên tải**. Đây là lý do phải đọc annotation và schema, không chỉ nhìn chữ `List`.

## 8. `Set`: mỗi phần tử chỉ xuất hiện một lần theo equality của Java

Khi nghiệp vụ yêu cầu “một cuốn sách có một tập các từ khóa, mỗi từ khóa chỉ có một lần”, `Set<String>` là lựa chọn trực tiếp.

~~~java
@ElementCollection
@CollectionTable(
    name = "book_keywords",
    joinColumns = @JoinColumn(name = "book_id")
)
@Column(name = "keyword", nullable = false, length = 50)
private Set<String> keywords = new HashSet<>();
~~~

Thao tác:

~~~java
keywords.add("java");
keywords.add("hibernate");
keywords.add("java");

System.out.println(keywords.size()); // 2
~~~

Điều này dựa trên ngữ nghĩa `String.equals()` và `String.hashCode()`. Với `HashSet`, **thứ tự duyệt không được đảm bảo**.

Khi lưu xuống database, ta có thể thiết kế ràng buộc để bảo vệ tính duy nhất thật sự:

~~~sql
CREATE TABLE book_keywords (
    book_id BIGINT NOT NULL REFERENCES tagged_books(id),
    keyword VARCHAR(50) NOT NULL,
    PRIMARY KEY (book_id, keyword)
);
~~~

Đoạn trên giả định bảng chủ `tagged_books` đã được tạo và khóa chính tên `id`. Đây là một thiết kế schema minh họa khi từ khóa là giá trị bất biến đơn giản; database khác hoặc mapping khác có thể cần ràng buộc khác.

**Đừng coi `Set` ở Java là thay thế cho `UNIQUE` tại database.** Một chương trình SQL khác có thể chèn dữ liệu bỏ qua Java collection; muốn chống trùng từ mọi đường ghi phải có khóa hoặc ràng buộc schema phù hợp.

### Vấn đề `equals()` và `hashCode()`

Với `Set<SomeValueObject>`, đối tượng nên có quy tắc bằng nhau dựa trên giá trị và nhất quán. Ví dụ hai mã sản phẩm `Sku("A-001")` nên được xem là cùng giá trị nếu nghiệp vụ định nghĩa như vậy.

Với `Set<SomeEntity>`, vấn đề khó hơn:

- Entity có thể chưa được cấp ID nếu dùng `@GeneratedValue`.
- `hashCode()` thay đổi sau khi thêm vào `HashSet` có thể khiến `contains` hoặc `remove` hoạt động sai.
- `equals()` dựa trên các field có thể thay đổi làm cấu trúc set mất tính ổn định.
- Hibernate proxy và đối tượng detached yêu cầu cách xử lý equality cẩn thận.

Ví dụ nguy hiểm nếu hash dựa vào ID sinh tự động và thay đổi sau persist:

~~~java
Set<Author> authors = new HashSet<>();
Author newAuthor = new Author("An"); // id có thể null.

authors.add(newAuthor);
em.persist(newAuthor); // Provider cấp id.

authors.contains(newAuthor); // Có thể false nếu hashCode đổi.
~~~

Không có một công thức `equals/hashCode` tối ưu cho mọi entity. Nhưng **không đặt thuộc tính mutable vào hash theo cách làm thay đổi vị trí phần tử trong set**, và phải hiểu vòng đời ID khi dùng collection entity.

### `Set` không phải giải pháp tự động cho thứ tự

`LinkedHashSet` thường giữ thứ tự thêm phần tử trong **một instance Java**; `TreeSet` sắp theo comparator. Tuy nhiên điều đó **không tự tạo cột thứ tự trong database**. Sau khi reload, dữ liệu có thể được đọc theo thứ tự khác, hoặc provider thay collection implementation.

Muốn một tập hợp có sắp xếp theo dữ liệu, cân nhắc `@OrderBy`, các cơ chế sorted set của Hibernate khi phù hợp, hoặc sắp xếp sau khi truy vấn. Nếu muốn lưu **thứ tự kéo thả độc lập với giá trị**, `List` có `@OrderColumn` thường đúng hơn.

## 9. `Map`: khóa riêng để tìm một giá trị

Một `Map<K,V>` có ngữ nghĩa khác `List` và `Set` vì mỗi entry mang **key** và **value**. Ví dụ một sách có tiêu đề theo mã ngôn ngữ:

~~~text
"vi" -> "Cẩm nang Hibernate"
"en" -> "Hibernate Handbook"
"ja" -> "Hibernate 入門"
~~~

Phía Java:

~~~java
Map<String, String> titles = new HashMap<>();
titles.put("vi", "Cẩm nang Hibernate");
titles.put("en", "Hibernate Handbook");

System.out.println(titles.get("vi")); // Cẩm nang Hibernate
~~~

Nếu gọi:

~~~java
titles.put("vi", "Sách Hibernate");
~~~

thì entry có key `"vi"` được **thay value**, không xuất hiện hai key `"vi"` trong cùng map. Trong khi đó, hai key khác nhau được phép cùng value.

### Ánh xạ `@ElementCollection` và `@MapKeyColumn`

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
import jakarta.persistence.MapKeyColumn;
import jakarta.persistence.Table;
import java.util.HashMap;
import java.util.Map;

@Entity
@Table(name = "localized_books")
public class LocalizedBook {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ElementCollection
    @CollectionTable(
        name = "book_localized_titles",
        joinColumns = @JoinColumn(name = "book_id")
    )
    @MapKeyColumn(name = "language_code", length = 10)
    @Column(name = "localized_title", length = 200)
    private Map<String, String> titlesByLanguage = new HashMap<>();

    protected LocalizedBook() {
    }

    public void putTitle(String language, String title) {
        titlesByLanguage.put(language, title);
    }

    public String titleIn(String language) {
        return titlesByLanguage.get(language);
    }
}
~~~

Cột `language_code` chứa **key**, cột `localized_title` chứa **value**:

| book_id | language_code | localized_title |
| ---: | --- | --- |
| 7 | vi | Cẩm nang Hibernate |
| 7 | en | Hibernate Handbook |
| 7 | ja | Hibernate 入門 |

Nếu cần bảo đảm mỗi sách chỉ có một tiêu đề cho mỗi ngôn ngữ, schema có thể dùng khóa:

~~~sql
CREATE TABLE book_localized_titles (
    book_id BIGINT NOT NULL REFERENCES localized_books(id),
    language_code VARCHAR(10) NOT NULL,
    localized_title VARCHAR(200),
    PRIMARY KEY (book_id, language_code)
);
~~~

Giả định bảng chủ đã được tạo. Ràng buộc `(book_id, language_code)` giúp tính duy nhất của key được bảo vệ cả khi thao tác trực tiếp bằng SQL.

**`@MapKeyColumn` không phải `@Column`.** Với `Map<String,String>` trong ví dụ, `@MapKeyColumn` đặt tên cột của **key** (`language_code`), còn `@Column` đặt tên cột của **value** (`localized_title`).

### Chọn key có ngữ nghĩa ổn định

Với map, key nên có quy tắc so sánh phù hợp (`equals/hashCode` hoặc comparator trong một số triển khai Java) và nên ổn định trong thời gian entry tồn tại. Nếu key là object mutable rồi sửa nó sau khi đã đưa vào `HashMap`, tra cứu có thể lỗi tương tự `HashSet`.

Thứ tự duyệt `Map` cũng là vấn đề riêng. `HashMap` không cam kết thứ tự; `LinkedHashMap` có thứ tự lặp ở Java nhưng không tự thêm cột index SQL. `Map` cơ bản hướng đến **tra cứu theo key**, không biểu thị danh sách có thứ tự bền vững.

## 10. `@MapKey` và `@MapKeyColumn` không giống nhau

Với collection giá trị `Map<String,String>`, `@MapKeyColumn` thường lưu key như một cột của bảng collection. Nhưng khi **value là một entity**, ta có thể muốn key lấy từ thuộc tính đã có của entity đó.

Ví dụ một cuốn sách có nhiều phiên bản xuất bản, mỗi `Edition` có mã `isbn`.

~~~java
@Entity
@Table(name = "editions")
public class Edition {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "book_id", nullable = false)
    private CatalogBook book;

    @Column(name = "isbn", nullable = false, unique = true)
    private String isbn;

    protected Edition() {
    }
}
~~~

Ở entity `CatalogBook`:

~~~java
@OneToMany(mappedBy = "book")
@MapKey(name = "isbn")
private Map<String, Edition> editionsByIsbn = new HashMap<>();
~~~

Ý nghĩa:

- `@MapKey(name = "isbn")` lấy thuộc tính `Edition.isbn` làm key trong map khi nạp.
- `isbn` là cột đã được ánh xạ trên entity `Edition`; không nhất thiết có một cột key thứ hai chỉ vì có `Map`.
- `@MapKeyColumn` là lựa chọn khác, dùng khi key được lưu **riêng trong collection/join table** theo mapping tương ứng.
- `mappedBy = "book"` nói rằng phía `Edition.book` nắm quan hệ FK; chỉ thêm phần tử vào map mà không cập nhật phía sở hữu có thể khiến hai phía không nhất quán.

**Cảnh báo với mutable `@MapKey`:** nếu mã `Edition.isbn` được thay đổi trong entity đang managed, Hibernate không tự bảo đảm cập nhật **key đã nằm trong Java map** ngay tức thì. Collection trong bộ nhớ có thể còn key cũ. Vì vậy hãy chọn map key ổn định hoặc chủ động giữ map đồng bộ và xác định quy tắc thay đổi khóa.

### `Map` không biến entity value thành value object

`Map<String,Edition>` là một collection **liên kết entity**; `Edition` vẫn có entity ID, transaction và vòng đời riêng. Ngược lại, `Map<String,String>` gắn `@ElementCollection` chứa các giá trị không có ID entity.

Cùng là `Map` Java nhưng loại mapping (*element collection* hay *association*) quyết định sơ đồ quan hệ và cách Hibernate ghi dữ liệu.

## 11. Quan hệ entity: `@OneToMany` và `@ManyToMany` còn thêm ràng buộc

Những ví dụ trước chủ yếu dùng `@ElementCollection`. Khi các phần tử là entity, cần phân biệt **ngữ nghĩa collection** với **ngữ nghĩa quan hệ database**.

Ví dụ một tác giả có nhiều bài viết:

~~~java
@Entity
public class Article {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "author_id", nullable = false)
    private Author author;

    protected Article() {
    }
}
~~~

Trong `Author`:

~~~java
@OneToMany(mappedBy = "author")
private List<Article> articles = new ArrayList<>();
~~~

Ở đây:

- `Article` là entity có khóa riêng.
- FK `article.author_id` xác định bài viết thuộc tác giả nào.
- `mappedBy` cho biết quan hệ được quản lý ở phía `Article.author`.
- Chữ `List` không làm các bài viết có cột vị trí. Nếu không có index mapping hoặc thứ tự cụ thể, không nên dựa vào thứ tự khi tải lại.

Điểm đặc biệt: **phần tử trong `@OneToMany` có ID riêng**. Hai lần thêm cùng một entity `Article` vào Java bag/list không nhất thiết có nghĩa database có thể lưu hai hàng quan hệ khác nhau trỏ tới cùng một bài viết, vì mỗi hàng `Article` chỉ có một FK `author_id`. Ngữ nghĩa bag cho phép trùng ở collection **không tự vượt qua ràng buộc quan hệ của schema**.

Với `@ManyToMany`, một bảng nối chứa các FK tới hai phía; tính duy nhất của một cặp khóa phụ thuộc mapping và ràng buộc trên bảng nối. Nếu ý nghĩa của mối liên kết cần có số lượng, thứ tự, thời gian hoặc trạng thái riêng, thường nên đưa **bảng nối thành một entity liên kết** thay vì chỉ dùng `@ManyToMany`.

### Cascade và xóa phần tử

- `@ElementCollection`: các hàng giá trị thuộc vòng đời của entity sở hữu. Xóa giá trị khỏi collection managed làm thay đổi nội dung collection lưu trữ khi transaction được đồng bộ thành công.
- `@OneToMany`: phần tử là entity. Xóa tham chiếu khỏi collection không luôn đồng nghĩa xóa hàng entity; cần xét phía sở hữu, `cascade`, `orphanRemoval` và ràng buộc FK.
- `@ManyToMany`: xóa phần tử khỏi một phía thường có ý nghĩa bỏ quan hệ trong bảng nối, không nhất thiết xóa entity bên kia.

Đừng chọn `Set` hay `List` như một cách thay cho việc hiểu `mappedBy`, cascade hoặc orphan removal. Collection semantics và lifecycle là **hai lớp quy tắc** có liên quan nhưng tách biệt.

## 12. So sánh hình dạng dữ liệu dưới database

Giả sử cuốn sách số 7 có ba loại dữ liệu:

~~~text
Chương có thứ tự:   ["A", "B", "A"]
Từ khóa không trùng: {"java", "jpa"}
Tiêu đề theo ngôn ngữ: {"vi":"Sách Java", "en":"Java Book"}
Ghi chú bag:        ["nháp", "xong", "nháp"] (không đòi thứ tự)
~~~

Các bảng có thể được thiết kế như sau:

~~~text
BOOK_CHAPTERS                          BOOK_KEYWORDS
+---------+----------+---------+       +---------+----------+
| book_id | position | heading |       | book_id | keyword  |
+---------+----------+---------+       +---------+----------+
| 7       | 0        | A       |       | 7       | java     |
| 7       | 1        | B       |       | 7       | jpa      |
| 7       | 2        | A       |       +---------+----------+
+---------+----------+---------+

BOOK_LOCALIZED_TITLES                   BOOK_NOTES
+---------+-------+-----------+         +---------+-----------+
| book_id | lang  | title     |         | book_id | note      |
+---------+-------+-----------+         +---------+-----------+
| 7       | vi    | Sách Java |         | 7       | nháp      |
| 7       | en    | Java Book |         | 7       | xong      |
+---------+-------+-----------+         | 7       | nháp      |
                                        +---------+-----------+
~~~

Trong **indexed list**, key nhận diện một vị trí thường gồm owner và index. Trong **map**, key nhận diện entry thường gồm owner và map key. Với **set giá trị**, ta có thể dùng owner và giá trị để xác định membership, nếu dữ liệu cho phép khóa như vậy. Với **bag**, cùng owner và cùng giá trị có thể xuất hiện nhiều lần nên bộ đôi đó không xác định duy nhất một *lần xuất hiện*.

Đây là lý do lựa chọn collection ảnh hưởng cả SQL và việc Hibernate có thể nhận ra hàng nào đã đổi.

## 13. Thao tác `add`, `remove`, `set` và `put` không tương đương

Giả sử các collection đã được Hibernate quản lý và mọi thay đổi diễn ra trong transaction phù hợp:

| Thao tác Java | Ngữ nghĩa | Hệ quả lưu trữ có thể có |
| --- | --- | --- |
| `list.add(0, x)` với `@OrderColumn` | Chèn ở đầu, dịch vị trí các phần tử khác | Chèn hàng và điều chỉnh nhiều index |
| `list.set(1, x)` với `@OrderColumn` | Thay giá trị tại vị trí 1 | Cập nhật giá trị hoặc thay hàng tại index |
| `set.add(x)` với phần tử đã bằng một phần tử hiện có | Không thêm phần tử mới | Không có thay đổi membership cần lưu |
| `set.remove(x)` | Xóa membership theo equality | Xóa hàng/mối liên kết tương ứng khi ORM đồng bộ |
| `map.put(k, v)` với key đã có | Ghi đè value cho key đó | Cập nhật entry gắn với key |
| `bag.add(x)` khi x đã tồn tại | Thêm **một lần xuất hiện nữa** | Có thể thêm hàng trùng giá trị |
| `bag.remove(x)` khi x xuất hiện nhiều lần | Với `Collection.remove(Object)`, xóa một phần tử phù hợp trong bộ nhớ | ORM cần đồng bộ số lần xuất hiện; có thể tốn nhiều SQL |
| `list.sort(...)` khi list có `@OrderColumn` | Thay đổi trình tự trong bộ nhớ | Có thể phải ghi lại index nếu thứ tự đổi |
| `list.sort(...)` chỉ có `@OrderBy` | Đổi trình tự đối tượng Java tạm thời | Không tự đổi thuộc tính được dùng trong `ORDER BY` |

**Câu lệnh SQL thực tế do Hibernate quyết định** và có thể khác trong từng mapping, phiên bản, chế độ batch và trạng thái collection. Bảng trên nói về ngữ nghĩa và chi phí có thể phát sinh, không cam kết số lượng SQL chính xác.

### Cẩn trọng với `remove(int)` và `remove(Object)`

Với `List<Integer>`, lệnh:

~~~java
list.remove(1);
~~~

thường được Java hiểu là **xóa theo chỉ số 1** nếu overload `remove(int)` được chọn, không phải “xóa giá trị Integer 1”. Nếu muốn xóa theo giá trị, gọi rõ:

~~~java
list.remove(Integer.valueOf(1));
~~~

Sự khác biệt này là hành vi của Java Collections, nhưng sẽ ảnh hưởng chính xác những thay đổi mà ORM phải ghi.

## 14. Tác động của trùng lặp khi tải bằng JOIN

Một truy vấn `JOIN` qua hai collection có thể tạo nhiều hàng kết quả do tích Descartes của quan hệ.

Ví dụ một `Book` có 3 ghi chú và 4 đánh giá:

~~~text
1 sách × 3 ghi chú × 4 đánh giá = 12 dòng SQL trung gian
~~~

Đó là tính chất thông thường của phép JOIN trên các quan hệ một-nhiều. Nhưng với **nhiều bag**, Hibernate gặp thêm vấn đề: bag không có index/khóa riêng cho từng lần xuất hiện để nhận ra khi nào hai hàng lặp là **bag duplicate thực sự** và khi nào là kết quả nhân bản do JOIN các collection khác.

Vì vậy, một số truy vấn Hibernate đồng thời `JOIN FETCH` nhiều bag có thể bị từ chối với:

~~~text
MultipleBagFetchException: cannot simultaneously fetch multiple bags
~~~

Ví dụ ý định nạp một lúc hai bag của cùng entity:

~~~java
select b
from NotedBook b
left join fetch b.notes
left join fetch b.comments
where b.id = :id
~~~

Đây là JPQL minh họa; `comments` giả định là collection bag khác đã được ánh xạ trên `NotedBook`. Vấn đề không phải cú pháp `left join` đơn lẻ, mà là **đồng thời fetch nhiều bag**.

Các cách xử lý tùy nhu cầu:

- Nạp một collection bằng join và nạp collection còn lại bằng truy vấn riêng.
- Dùng batch fetching hoặc subselect fetching của Hibernate khi phù hợp.
- Truy vấn một DTO/projection theo đúng dữ liệu cần hiển thị thay vì lấy mọi collection trong một câu lệnh.
- Thiết kế lại collection thành list có index hoặc set **chỉ khi nghiệp vụ thật sự có ngữ nghĩa đó**.

**Không đổi `List` thành `Set` chỉ để né `MultipleBagFetchException` nếu dữ liệu cần giữ phần tử trùng.** Làm vậy có thể khiến dữ liệu bị loại bớt theo equality, thay đổi kết quả nghiệp vụ. Dù query không còn báo lỗi, nhiều collection fetch join vẫn có thể tạo kết quả SQL rất lớn và gây vấn đề hiệu năng.

## 15. Lazy loading, N+1 và phạm vi transaction

Collection entity và element collection thường có thể được nạp trễ, tùy kiểu mapping và cách truy vấn. Giả sử lấy 100 cuốn sách rồi duyệt toàn bộ keywords:

~~~java
List<TaggedBook> books =
    em.createQuery("select b from TaggedBook b", TaggedBook.class)
      .getResultList();

for (TaggedBook book : books) {
    System.out.println(book.getKeywords().size());
}
~~~

Nếu mỗi collection chưa được tải và Hibernate thực hiện một query riêng cho mỗi sách, ứng dụng có thể gặp **N+1 query**: một truy vấn lấy danh sách sách, rồi nhiều truy vấn bổ sung.

Việc chọn `List`, `Set`, `Map` hoặc bag **không tự loại bỏ N+1**. Cần cân nhắc cách fetch và phạm vi truy cập:

- Chỉ lấy collection cần thiết cho màn hình hoặc nghiệp vụ hiện tại.
- Dùng fetch join phù hợp khi số collection và số hàng liên quan nhỏ.
- Dùng batch fetch, subselect hoặc DTO projection theo cấu hình Hibernate nếu cần.
- Kiểm soát số lượng phần tử để tránh tải một collection quá lớn chỉ nhằm tính count hoặc kiểm tra tồn tại.
- Đặt thao tác truy cập dữ liệu trong phạm vi persistence context và transaction phù hợp.

Khi context đã đóng, truy cập collection lazy chưa được nạp có thể dẫn đến `LazyInitializationException`. Đừng giải quyết bằng cách chuyển tất cả collection thành `EAGER`; nạp dữ liệu sớm hàng loạt có thể tăng chi phí query và tạo các vấn đề fetch khác.

## 16. Một số lựa chọn bổ sung: collection có thứ tự theo giá trị

Có những nhu cầu muốn **sắp theo giá trị** nhưng không cần một chỉ số người dùng kéo thả. Lúc ấy có thể chọn:

- `@OrderBy`: provider định nghĩa thứ tự đọc theo thuộc tính/giá trị, thường thông qua `ORDER BY` của SQL.
- `SortedSet` hoặc `SortedMap`: Java có comparator/natural ordering; Hibernate hỗ trợ các mapping sắp xếp chuyên biệt ở một số cấu hình, chẳng hạn `@SortNatural` hoặc `@SortComparator`.
- Truy vấn trả DTO đã sắp xếp bằng JPQL/SQL `ORDER BY` rồi xây dựng collection phía ứng dụng.

Ba hướng trên khác `@OrderColumn` ở chỗ **thứ tự được tính theo tiêu chí** hoặc kết quả truy vấn, chứ không nhất thiết lưu một vị trí liên tục của từng lần xuất hiện.

Ví dụ các đánh giá sắp theo thời điểm:

~~~java
@OneToMany(mappedBy = "book")
@OrderBy("createdAt ASC, id ASC")
private List<BookReview> reviews = new ArrayList<>();
~~~

Nếu người dùng muốn kéo “đánh giá cũ” lên trước đánh giá mới dù `createdAt` không đổi, `@OrderBy` không biểu diễn được mong muốn ấy. Khi đó cần mô hình thứ tự được lưu riêng, ví dụ indexed list hoặc trường position nghiệp vụ trên entity con.

Các annotation sắp xếp như `@SortNatural` là **đặc thù Hibernate**, khác API chuẩn Jakarta Persistence. Cần chọn theo mục tiêu tính di động của dự án.

## 17. Kiểu collection còn quyết định cách thay đổi được phát hiện

Khi Hibernate nạp một collection, nó theo dõi trạng thái để đồng bộ thay đổi lúc flush. Cách nhận diện phần tử liên quan đến collection semantics:

- **Indexed list:** có vị trí, nên có thể so sánh membership và index. Reorder làm thay đổi index, kể cả giá trị không đổi.
- **Set:** thay đổi membership dựa trên equality. Một phần tử có hash không ổn định khiến collection Java hành xử sai trước khi tới Hibernate.
- **Map:** thay đổi theo key và value; key cần ổn định. Thay key thường mang ý nghĩa xóa entry cũ và thêm entry mới.
- **Bag:** cho phép nhiều bản sao theo giá trị; thiếu index khiến ORM khó xác định một lần xuất hiện cụ thể, đặc biệt khi row database không có khóa riêng.

Với collection chứa `@Embeddable` mutable, cần xem kỹ `equals`, chiến lược snapshot và cách sửa từng thành phần. Với collection chứa entity, cần xét ID, equality, proxy và relationship ownership. Không nên biến tất cả vấn đề dirty checking thành chuyện “thêm setter” hoặc “đổi Collection thành List”; ngữ nghĩa collection, trạng thái managed và mapping thực tế mới quyết định cách đồng bộ.

### Thay instance collection có an toàn không?

Nên thao tác trên collection do entity sở hữu:

~~~java
book.getKeywords().add("hibernate");
~~~

thay vì tùy tiện thay cả field:

~~~java
book.setKeywords(new HashSet<>(incomingKeywords));
~~~

Cách thay field có thể làm Hibernate mất wrapper collection cũ, ảnh hưởng đến tracking, cascade/orphan removal hoặc tạo nhiều SQL hơn, tùy mapping và trạng thái entity. Điều đó **không có nghĩa thay collection luôn sai**, nhưng khi quản lý aggregate thường an toàn hơn nếu cung cấp phương thức nghiệp vụ chỉnh membership của collection hiện tại.

Đối với `@OneToMany(orphanRemoval = true)`, thay hẳn collection reference trên managed entity có thể gây lỗi khi Hibernate theo dõi orphan. Những phương thức như `addChild`/`removeChild` còn giúp đồng bộ cả hai phía của quan hệ hai chiều.

## 18. Chọn collection theo câu hỏi nghiệp vụ

Một số nhu cầu điển hình:

| Yêu cầu | Lựa chọn khởi đầu | Vì sao |
| --- | --- | --- |
| Người dùng kéo thả thứ tự chương của tài liệu | `List` + `@OrderColumn` | Vị trí là một phần dữ liệu cần lưu |
| Từ khóa không được trùng | `Set<String>` | Membership, không có nhiều bản sao của cùng keyword |
| Ghi chú có thể trùng và thứ tự không có ý nghĩa | Bag/`Collection<String>` | Giữ số lần xuất hiện mà không lưu index |
| Tiêu đề theo mã ngôn ngữ | `Map<String,String>` + `@MapKeyColumn` | Tra cứu trực tiếp bằng language key |
| Danh sách thông báo luôn xem mới nhất trước | `@OrderBy("createdAt DESC")` trên association | Sort theo dữ liệu, không phải vị trí kéo thả |
| Quyền của người dùng không lặp | `Set<Role>` với entity relationship | Tránh trùng membership; cần xem equality của entity |
| Sản phẩm trong giỏ có số lượng | Entity dòng giỏ hàng với `quantity` | Số lượng là thuộc tính quan hệ, rõ hơn lặp product trong bag |
| Nhiều phiên bản theo mã `isbn` | `Map<String,Edition>` + `@MapKey` | Key lấy từ thuộc tính có sẵn của entity |
| Một collection rất lớn cần paging | Truy vấn repository/DTO riêng | Không nên tải toàn bộ collection chỉ để phân trang |

**Cẩn thận với “giỏ hàng là bag của Product”.** Hai lần xuất hiện cùng product có thể được hiểu là số lượng 2, nhưng trong nghiệp vụ thực, dòng giỏ hàng còn có đơn giá tại thời điểm mua, chiết khấu, số lượng, trạng thái và nhiều ràng buộc. Một `CartItem` entity hoặc `@Embeddable` có số lượng rõ ràng thường dễ quản lý hơn nhiều bản sao không có identity trong bag.

### Quy trình quyết định

~~~mermaid
flowchart TD
    A["Một thuộc tính cần chứa nhiều phần tử"] --> B{"Cần tra cứu theo key riêng?"}
    B -- "Có" --> M["Map<K,V> và mapping key phù hợp"]
    B -- "Không" --> C{"Có cần phần tử trùng?"}
    C -- "Không" --> S["Set<T> và equality ổn định"]
    C -- "Có" --> D{"Có cần lưu thứ tự vị trí?"}
    D -- "Có" --> L["List<T> với @OrderColumn"]
    D -- "Không" --> G["Bag / Collection<T>"]
    S --> E["Chọn ElementCollection hay entity association"]
    L --> E
    G --> E
    M --> E
    E --> F["Định nghĩa schema, ràng buộc, fetch và transaction"]
~~~

Quy trình này là bước chọn ngữ nghĩa cơ bản. Nếu collection có entity con, thứ tự theo field khác, khóa ghép hoặc yêu cầu cập nhật số lượng theo dòng, còn phải xét domain và quan hệ thực tế.

## 19. Bài thực hành: cùng một tập giá trị qua bốn cách ánh xạ

Cho dữ liệu:

~~~text
"A", "B", "A"
~~~

Hãy xác định ý nghĩa khi lưu bằng bốn collection.

### Trường hợp A — `List` có `@OrderColumn`

~~~java
List<String> values = new ArrayList<>(List.of("A", "B", "A"));
~~~

Mapping:

~~~java
@ElementCollection
@CollectionTable(name = "values_list", joinColumns = @JoinColumn(name = "owner_id"))
@OrderColumn(name = "value_index")
@Column(name = "value_text")
private List<String> values = new ArrayList<>();
~~~

Ý nghĩa: có ba **vị trí** `0,1,2`; hai vị trí cùng chứa `"A"`. Khi gọi `Collections.swap(values, 0, 1)`, thứ tự trở thành `B,A,A` và mapping có thông tin cần thiết để lưu vị trí mới.

### Trường hợp B — `Set`

~~~java
Set<String> values = new HashSet<>();
values.add("A");
values.add("B");
values.add("A");
~~~

Kết quả `size() == 2`, vì `"A"` xuất hiện một lần theo equality của Java. Thứ tự duyệt của `HashSet` không được đảm bảo.

### Trường hợp C — Bag

~~~java
Collection<String> values = new ArrayList<>();
values.add("A");
values.add("B");
values.add("A");
~~~

Kết quả có ba lần xuất hiện. Mapping bag cho phép lưu hai `"A"`, nhưng không có chỉ số bền vững. Sau reload không được lấy vị trí làm cơ sở nghiệp vụ.

### Trường hợp D — `Map`

~~~java
Map<String, String> values = new HashMap<>();
values.put("first", "A");
values.put("second", "B");
values.put("third", "A");
~~~

Ở đây có **ba entry**, vì ba **key khác nhau**. Hai value `"A"` là hợp lệ.

Nếu thay:

~~~java
values.put("first", "C");
~~~

thì map vẫn có ba key; key `first` chuyển từ value `A` sang `C`. Chữ “trùng” trong map phải phân biệt **trùng key** với **trùng value**.

## 20. Tự kiểm tra kiến thức

**Câu 1.** Một field Java là `List<String>`, không có `@OrderColumn`. Có thể chắc chắn thứ tự `add(...)` sẽ được giữ sau khi nạp lại không?

**Trả lời:** Không. Java `List` có thứ tự trong bộ nhớ, nhưng mapping không có cột index thì không có thông tin vị trí bền vững. Với Hibernate, dạng này có thể mang bag semantics tùy cấu hình.

**Câu 2.** `@OrderBy("createdAt DESC")` có khác `@OrderColumn(name="position")` không?

**Trả lời:** Có. `@OrderBy` sắp xếp khi đọc dựa trên giá trị thuộc tính; `@OrderColumn` lưu một index để tái tạo vị trí và hỗ trợ reorder.

**Câu 3.** Một bag có hai phần tử giống nhau. Vì sao việc xóa một phần tử có thể tốn nhiều SQL?

**Trả lời:** Nếu bảng không có khóa riêng cho từng lần xuất hiện, ORM khó xác định hàng nào là bản sao cần xóa. Một số mapping có thể phải xóa và tạo lại các hàng collection.

**Câu 4.** `Set` Java có thay thế ràng buộc unique trong database không?

**Trả lời:** Không. `Set` bảo vệ membership theo equality trong bộ nhớ; database cần ràng buộc riêng nếu muốn chống trùng cho mọi đường ghi.

**Câu 5.** Với `Map<String,String>`, `@MapKeyColumn` xác định cột nào?

**Trả lời:** Cột lưu key, ví dụ `language_code`; `@Column` trên element collection map xác định cột lưu value.

**Câu 6.** Với `@MapKey(name="isbn")` trên `Map<String,Edition>`, key lấy ở đâu?

**Trả lời:** Từ thuộc tính entity `Edition.isbn`, là một property đã được ánh xạ; không mặc định tạo một cột key mới độc lập.

**Câu 7.** Có nên chuyển hai bag sang `Set` chỉ vì query ném `MultipleBagFetchException`?

**Trả lời:** Không nếu nghiệp vụ cho phép trùng. Nên xem cách fetch: tách query, batching, subselect hoặc projection; chỉ đổi collection semantics khi đúng với dữ liệu.

**Câu 8.** Nếu một Java `List` được sort lại trong bộ nhớ nhưng mapping chỉ có `@OrderBy("name")`, ORM có tự thay `name` để giữ thứ tự mới không?

**Trả lời:** Không. Thứ tự sau tải lại vẫn theo `name`; phải cập nhật giá trị sắp xếp hoặc dùng thiết kế lưu vị trí riêng.

**Câu 9.** Vì sao không nên dùng một `Set<Entity>` khi `equals/hashCode` thay đổi theo generated ID từ null sang giá trị thật?

**Trả lời:** Hash của phần tử có thể thay đổi sau khi nó đã nằm trong `HashSet`, làm các thao tác `contains/remove` không còn tìm đúng phần tử.

**Câu 10.** Một giỏ hàng có hai lần chọn cùng sản phẩm. Bag hay entity dòng giỏ hàng phù hợp hơn?

**Trả lời:** Nếu chỉ cần lưu số lần xuất hiện và không có thuộc tính khác, bag có thể biểu diễn được số lần lặp. Trong giỏ hàng thực tế cần quantity, đơn giá và quy tắc nghiệp vụ, một entity/giá trị dòng giỏ hàng với thuộc tính số lượng thường rõ nghĩa và dễ bảo trì hơn.

## 21. Điều cần nhớ khi đọc mapping Hibernate

**`List`, `Set`, `Map` và bag không chỉ là lựa chọn collection Java, mà còn là lựa chọn về ngữ nghĩa dữ liệu lưu trữ.**

- `List` **có chỉ số được lưu** khi dùng ánh xạ phù hợp như `@OrderColumn`; đây là lựa chọn cho thứ tự vị trí cần bền vững.
- `Set` xác định **membership duy nhất theo equality**, không mặc định có thứ tự; tính duy nhất ở database còn cần ràng buộc schema tương ứng.
- `Map` xác định **giá trị theo key**; hiểu rõ `@MapKeyColumn`, `@MapKey` và việc key có thể thay đổi.
- **Bag** cho phép **lặp** nhưng **không có chỉ số lưu trữ**; nhiều lần xuất hiện giống nhau có thể khiến thao tác cập nhật và fetch phức tạp hơn.
- `@OrderBy` mô tả **sắp xếp theo giá trị khi đọc**, khác với `@OrderColumn` lưu vị trí. Hai khái niệm không thể dùng thay thế chỉ bằng cách đổi annotation.
- Ngữ nghĩa collection phải được đặt trong bối cảnh `@ElementCollection` hay entity association, khóa ngoại, cascade, schema, cách fetch và transaction.

Khi thiết kế một collection, hãy bắt đầu từ câu hỏi **“dữ liệu có trùng được không, cần giữ thứ tự nào, và mỗi phần tử có key riêng không?”**. Trả lời đúng ba câu hỏi này sẽ giúp lựa chọn kiểu collection và mapping tương ứng, tránh mất thứ tự sau tải lại, xóa nhầm phần tử trùng hoặc gây chi phí SQL ngoài dự kiến.
