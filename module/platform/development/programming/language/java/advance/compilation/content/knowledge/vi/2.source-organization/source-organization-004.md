# Tổ chức nhiều tệp Java có tham chiếu qua lại

Một chương trình Java thực tế hiếm khi chỉ có một tệp. Một lớp có thể gọi phương thức của lớp trong tệp khác; hai lớp thậm chí có thể cùng biết kiểu của nhau. Để biên dịch và chạy đúng, cần phân biệt **tệp nguồn**, **lớp/kiểu Java**, **package**, **đường dẫn tìm nguồn**, **đường dẫn tìm lớp đã biên dịch**, và **phụ thuộc ở thời điểm chạy**.

Bài này sử dụng Java 17 trở lên, tập trung vào cách bố trí, tham chiếu, biên dịch và xử lý lỗi khi các tệp nguồn phụ thuộc lẫn nhau.

## 1. Một tệp Java tham chiếu tệp khác như thế nào?

Giả sử tệp \`Book.java\` định nghĩa kiểu \`Book\`, còn \`Main.java\` tạo đối tượng \`Book\`. Mã trong \`Main\` tham chiếu **kiểu \`Book\`**, chứ không “nhúng tệp” theo cách \`#include\` trong C/C++.

Trình biên dịch \`javac\` đọc khai báo kiểu, kiểm tra tên, khả năng truy cập, chữ ký phương thức và các ràng buộc kiểu. Nó có thể xử lý nhiều tệp nguồn trong **cùng một lần biên dịch**. Kết quả thường là các tệp \`.class\` chứa bytecode; JVM nạp lớp cần thiết khi chạy.

Ba quan hệ cần phân biệt:

- **Phụ thuộc kiểu ở lúc biên dịch:** \`Book\` khai báo một trường kiểu \`Author\`; trình biên dịch phải tìm và kiểm tra \`Author\`.
- **Tham chiếu đối tượng ở lúc chạy:** một đối tượng \`Book\` giữ tham chiếu đến một đối tượng \`Author\`. Hai đối tượng có thể giữ tham chiếu qua lại.
- **Phụ thuộc giữa module/thư viện:** dự án A cần thư viện B trên classpath/module path. Quy tắc cấu hình và tính chu trình của tầng này khác với quan hệ giữa hai lớp.

**Một cặp lớp tham chiếu kiểu qua lại không tự động gây lỗi biên dịch.** Điều quan trọng là các khai báo hợp lệ, có thể tìm thấy và truy cập được; cách khởi tạo đối tượng cũng phải hợp lý.

## 2. Quy tắc đặt tệp, package và thư mục

Với lớp top-level \`public\` tên \`Book\`, tên tệp nguồn phải là \`Book.java\`. Nếu đầu tệp khai báo \`package vn.lesson.domain;\`, hãy đặt tệp theo cấu trúc \`src/vn/lesson/domain/Book.java\`. Phần \`src\` là **gốc nguồn** (source root), không phải thành phần tên package.

Một tổ chức điển hình:

~~~text
project/
├── src/
│   └── vn/
│       └── lesson/
│           ├── domain/
│           │   ├── Author.java
│           │   └── Book.java
│           ├── service/
│           │   └── BookCatalog.java
│           └── app/
│               └── Main.java
└── out/                 # tạo khi biên dịch
~~~

Quy tắc nền tảng:

1. Dòng \`package\` (nếu có) đứng trước các \`import\` và khai báo kiểu, ngoại trừ chú thích.
2. Hai kiểu trong **cùng package** có thể gọi nhau bằng tên đơn \`Author\`, \`Book\` mà không cần \`import\`, dù chúng ở hai tệp riêng.
3. Với kiểu ở package khác, dùng \`import vn.lesson.domain.Book;\` hoặc tên đầy đủ \`vn.lesson.domain.Book\`.
4. \`import vn.lesson.domain.*;\` chỉ xét các kiểu có thể truy cập trực tiếp trong package đó; không tự động nhập subpackage.
5. Tên package phân biệt chữ hoa/chữ thường. Trên hệ thống tệp phân biệt hoa/thường, \`domain\` và \`Domain\` là hai đường dẫn khác nhau.
6. Không nên dùng package mặc định (không có dòng \`package\`) cho ứng dụng nhiều tệp; lớp trong package có tên không thể nhập lớp ở package mặc định.
7. Một tệp có thể chứa nhiều kiểu top-level package-private, nhưng chỉ tối đa một kiểu top-level \`public\`; thông thường nên tách mỗi kiểu chính ra một tệp dễ tìm.

\`src/\` chứa mã nguồn, còn \`out/\` chỉ chứa kết quả biên dịch. Giữ chúng tách biệt để tránh nhầm giữa các bản \`.class\` cũ và nguồn mới.

## 3. Ví dụ hoàn chỉnh: bốn tệp, các lớp tham chiếu qua lại

Yêu cầu: \`Author\` biết cuốn sách nổi bật của mình; \`Book\` biết tác giả; \`BookCatalog\` trình bày thông tin sách; \`Main\` phối hợp các đối tượng. Trong đó \`Author\` và \`Book\` **tham chiếu kiểu qua lại** ngay trong hai tệp khác nhau. Tạo bốn tệp đúng đường dẫn ở phần 2.

### 3.1. \`src/vn/lesson/domain/Author.java\`

~~~java
package vn.lesson.domain;

public final class Author {
    private final String name;
    private Book featuredBook;

    public Author(String name) {
        this.name = name;
    }

    public String name() {
        return name;
    }

    public void feature(Book book) {
        if (book == null || book.author() != this) {
            throw new IllegalArgumentException(
                "Book must belong to this author"
            );
        }
        this.featuredBook = book;
    }

    public String featuredTitle() {
        return featuredBook == null
            ? "(chưa có)"
            : featuredBook.title();
    }
}
~~~

\`Author\` sử dụng trực tiếp kiểu \`Book\` trong trường, tham số và lời gọi phương thức. Không cần nhập \`Book\` vì hai kiểu cùng package \`vn.lesson.domain\`. Trường \`featuredBook\` ban đầu là \`null\`; ta nối quan hệ sau khi tạo \`Book\`, tránh phụ thuộc vào đối tượng chưa tồn tại.

### 3.2. \`src/vn/lesson/domain/Book.java\`

~~~java
package vn.lesson.domain;

import java.util.Objects;

public final class Book {
    private final String title;
    private final Author author;

    public Book(String title, Author author) {
        this.title = Objects.requireNonNull(title, "title");
        this.author = Objects.requireNonNull(author, "author");
    }

    public String title() {
        return title;
    }

    public Author author() {
        return author;
    }
}
~~~

\`Book\` cũng tham chiếu \`Author\`, tạo ra quan hệ hai chiều **giữa các khai báo kiểu**. \`Objects.requireNonNull\` đảm bảo hai tham số bắt buộc không null; đó là lời gọi thư viện chuẩn \`java.util.Objects\`.

### 3.3. \`src/vn/lesson/service/BookCatalog.java\`

~~~java
package vn.lesson.service;

import vn.lesson.domain.Book;

public final class BookCatalog {
    public String label(Book book) {
        return book.title() + " — " + book.author().name();
    }
}
~~~

\`BookCatalog\` thuộc package khác nên nhập kiểu công khai \`Book\`. Nó không cần biết đường dẫn tệp \`Book.java\`, cũng không cần \`import Author\` vì không sử dụng trực tiếp tên kiểu \`Author\` trong khai báo hoặc biểu thức.

### 3.4. \`src/vn/lesson/app/Main.java\`

~~~java
package vn.lesson.app;

import vn.lesson.domain.Author;
import vn.lesson.domain.Book;
import vn.lesson.service.BookCatalog;

public final class Main {
    public static void main(String[] args) {
        Author author = new Author("Lan");
        Book book = new Book("Java 17", author);
        author.feature(book);

        System.out.println(new BookCatalog().label(book));
        System.out.println(author.featuredTitle());
        System.out.println(book.author() == author);
    }
}
~~~

Cấu trúc phụ thuộc kiểu:

~~~text
app.Main ──> domain.Author
         ├─> domain.Book <──> domain.Author
         └─> service.BookCatalog ──> domain.Book
~~~

Mũi tên hai chiều giữa \`Book\` và \`Author\` nói về khả năng tham chiếu kiểu. Khi chạy, biến \`book.author\` và \`author.featuredBook\` trỏ qua lại đến hai đối tượng đã khởi tạo; phép \`==\` cuối cùng kiểm tra chúng có trỏ đúng cùng đối tượng \`Author\` không.

## 4. Biên dịch và chạy từ thư mục \`project\`

Yêu cầu JDK 17 trở lên; kiểm tra bằng \`javac -version\` và \`java -version\`. Mở terminal tại thư mục \`project\` (nơi chứa \`src\`). Tạo thư mục đầu ra rồi truyền tất cả tệp nguồn cho **một lời gọi \`javac\`**:

~~~sh
mkdir out
javac --release 17 -encoding UTF-8 -d out src/vn/lesson/domain/Author.java src/vn/lesson/domain/Book.java src/vn/lesson/service/BookCatalog.java src/vn/lesson/app/Main.java
java -cp out vn.lesson.app.Main
~~~

Kết quả chuẩn:

~~~text
Java 17 — Lan
Java 17
true
~~~

Ví dụ đã được kiểm chứng biên dịch với \`--release 17\` và cho đúng ba dòng kết quả trên.

Giải nghĩa các phần trong lệnh:

- \`--release 17\`: kiểm tra ngôn ngữ và API theo nền tảng Java 17; giúp tránh vô tình dùng API chỉ có ở JDK mới hơn.
- \`-encoding UTF-8\`: mã hóa khi \`javac\` đọc tệp \`.java\`; điều này rất hữu ích nếu có dấu tiếng Việt hoặc ký tự Unicode trong mã.
- \`-d out\`: xuất \`.class\` vào gốc \`out\`, giữ lại cây package, ví dụ \`out/vn/lesson/domain/Book.class\`.
- \`-cp out\`: đưa gốc chứa các package đã biên dịch lên **classpath lúc chạy**.
- \`vn.lesson.app.Main\`: tên lớp đầy đủ, gồm package; **không** truyền \`src/.../Main.java\` hoặc \`Main.class\` cho cách chạy này.

Thứ tự liệt kê bốn tệp cho cùng một lần gọi \`javac\` **không phải** thứ tự biên dịch bắt buộc giữa các lớp. Trình biên dịch giải quyết các tham chiếu kiểu trong toàn bộ tập nguồn đã cho. Không cần biên dịch \`Author\` trước \`Book\`, hoặc ngược lại.

Lưu ý về terminal trên Windows: đường dẫn dấu \`/\` ở lệnh trên được Java chấp nhận; có thể dùng \`\\\` thay cho dấu phân cách thư mục khi cần. Trong PowerShell 5, một số lệnh ghi tệp \`-Encoding UTF8\` thêm BOM; \`javac\` có thể báo \`illegal character: '\uFEFF'\` ở đầu tệp. Nên lưu \`.java\` bằng UTF-8 **không BOM**.

### 4.1. Khi chỉ chỉ định tệp \`Main.java\`

Có thể cho \`javac\` tự tìm các tệp nguồn phụ thuộc trong source root:

~~~sh
javac --release 17 -encoding UTF-8 -sourcepath src -d out src/vn/lesson/app/Main.java
java -cp out vn.lesson.app.Main
~~~

\`-sourcepath src\` cho biết nơi tìm \`.java\` của các kiểu được tham chiếu nhưng chưa có dạng \`.class\` phù hợp. Ví dụ này dùng cùng bốn tệp ở phần 3, với thư mục \`out\` đã được tạo.

Khác biệt quan trọng:

| Tham số | Vai trò |
|---|---|
| \`-sourcepath src\` | Nơi \`javac\` tìm nguồn \`.java\` phụ thuộc. |
| \`-classpath out\` hoặc \`-cp out\` | Nơi \`javac\` hoặc \`java\` tìm các lớp/thư viện đã biên dịch, tùy lệnh. |
| \`-d out\` | Nơi \`javac\` ghi \`.class\` mới. |
| \`--module-path\` | Nơi tìm các Java module đã biên dịch, trong dự án dùng Java Platform Module System (JPMS). |

Nếu không đặt \`-sourcepath\`, việc \`javac\` tìm nguồn phụ thuộc phụ thuộc vào cấu hình classpath/source path mặc định. Đừng dựa vào việc compiler tình cờ tìm thấy tệp ở một thư mục khác. Với dự án vừa và lớn, nên để Maven/Gradle xác định source sets và classpath nhất quán.

## 5. Cách Java giải quyết tên và quyền truy cập

Biên dịch thành công không chỉ đòi hỏi tìm đúng tệp; kiểu và thành viên được dùng phải **truy cập được**:

- \`public\` top-level class: có thể dùng từ package khác, với điều kiện kiểu đó hiện diện trên đường dẫn biên dịch và, nếu dùng JPMS, package được export phù hợp.
- Top-level class không có \`public\`: chỉ truy cập được từ cùng package.
- Thành viên \`private\`: chỉ truy cập theo quy tắc phạm vi của lớp/nest được phép; việc đặt hai lớp trong cùng package không cho lớp kia dùng thành viên \`private\`.
- Thành viên không ghi modifier (package-private): truy cập được trong cùng package.
- \`protected\`: có quy tắc riêng cho cùng package và cho lớp con ở package khác; không đồng nghĩa với \`public\`.
- \`import\` chỉ cho phép dùng tên ngắn hơn; nó **không** cấp quyền truy cập, không đưa thư viện lên classpath, không tự tạo lớp và không thực thi mã.

Ví dụ, \`BookCatalog\` không thể gọi \`book.author\` vì đó là trường \`private\`; nó gọi phương thức \`public author()\` thay thế.

Nếu có hai lớp cùng tên ở hai package, có thể dùng tên đầy đủ để tránh mơ hồ, chẳng hạn \`java.util.Date\` và \`java.sql.Date\`. Package cha và package con độc lập về quyền truy cập: \`vn.lesson\` và \`vn.lesson.domain\` **không** được xem là cùng package.

## 6. “Tham chiếu qua lại” hợp lệ và các chu trình cần tránh

### 6.1. Quan hệ kiểu hai chiều khác với vòng lặp lúc chạy

Trong ví dụ, \`Author\` khai báo \`Book featuredBook\`, còn \`Book\` khai báo \`Author author\`. Đó là một **chu trình quan hệ giữa các kiểu**, hợp lệ với Java. Chương trình chỉ gọi \`feature\` sau khi đã tạo đủ hai đối tượng.

Không nên suy luận rằng mọi kiểu chu trình đều hợp lệ:

- Hai lớp cố gắng \`extends\` nhau trực tiếp hoặc gián tiếp sẽ bị từ chối vì **kế thừa vòng**.
- Hai constructor tạo lẫn nhau vô điều kiện (\`new A()\` trong constructor A gọi \`new B()\`, rồi constructor B lại \`new A()\`) có thể dẫn đến \`StackOverflowError\`.
- Getter \`A.toString()\` gọi \`B.toString()\` rồi \`B.toString()\` gọi ngược lại có thể gây đệ quy vô hạn.
- Khởi tạo trường \`static\` xuyên qua nhiều lớp có thể đọc giá trị mặc định trước khi khởi tạo xong, hoặc phát sinh lỗi khởi tạo. Cần hiểu thứ tự khởi tạo theo Java Language Specification.
- Serializer, logger và phép so sánh đi sâu vào toàn bộ đồ thị đối tượng có thể lặp vô hạn nếu không xử lý chu trình.

**Quy tắc thực hành:** tham chiếu qua lại chỉ nên xuất hiện khi mô hình dữ liệu có quan hệ hai chiều thực sự cần thiết. Tách bước tạo đối tượng khỏi bước nối quan hệ nếu khởi tạo tuần tự có thể gây vòng gọi constructor.

### 6.2. Phụ thuộc hai chiều làm thiết kế khó bảo trì

Hai class tham chiếu kiểu qua lại có thể biên dịch được, nhưng nếu nhiều package cứ gọi chéo mọi nơi thì mã sẽ khó kiểm thử và khó thay đổi. Với hệ thống có tầng \`app → service → repository\`, thường nên giữ chiều phụ thuộc ổn định:

~~~text
app/Main  --->  service/BookService  --->  domain/Book
                           |
                           +----> repository/BookRepository (interface)
                                          ^
                                          |
                              repository/InMemoryBookRepository
~~~

Đây là sơ đồ định hướng thiết kế, **không phải** các tệp bổ sung của ví dụ chạy ở phần 3. Một interface ở tầng phù hợp giúp thành phần cấp cao phụ thuộc vào hợp đồng thay vì class triển khai cụ thể. Khi không cần truy cập từ đối tượng A sang B và ngược lại, chỉ lưu một chiều, hoặc truyền dữ liệu vào tham số phương thức, thường đơn giản hơn.

Trong Maven/Gradle, vòng phụ thuộc **giữa các project/module** là vấn đề khác: build tool, JPMS và thiết kế kiến trúc có những quy tắc riêng. Đừng lấy việc hai lớp cùng biên dịch để kết luận rằng hai Java module có thể \`requires\` lẫn nhau; JPMS không cho phép chu trình module dạng đó.

## 7. Biên dịch tách đợt, thư viện ngoài và JPMS

Ví dụ dùng một lần \`javac\` với đủ các tệp nguồn. Khi triển khai thành nhiều đợt, lớp đã biên dịch trong đợt trước phải có mặt trên **compile classpath** của đợt sau. Ví dụ muốn biên dịch \`Main.java\` sau khi đã có \`Book\`, \`Author\`, \`BookCatalog\` trong \`out\`:

~~~sh
javac --release 17 -encoding UTF-8 -cp out -d out src/vn/lesson/app/Main.java
~~~

Lệnh này **chỉ** đúng khi \`out\` đã chứa bytecode tương thích của các lớp phụ thuộc. Nếu \`out\` chưa có chúng và không thiết lập \`-sourcepath\`, \`javac\` sẽ báo không tìm thấy ký hiệu hoặc package. Nếu thay đổi API của lớp phụ thuộc, phải biên dịch lại các phần liên quan; đừng dựa vào \`.class\` cũ.

Với JAR ngoài, thêm thư viện vào classpath khi biên dịch và khi chạy nếu ứng dụng cần lớp đó lúc chạy. Trên Windows, các mục classpath ngăn cách bằng \`;\`; trên Linux/macOS bằng \`:\`. Không nhầm các dấu phân cách này với \`.\` trong tên package.

Khi chuyển sang **named modules** (\`module-info.java\`), cần mô tả \`requires\` cho module khác và \`exports\` cho package công khai muốn module khác dùng. \`import\` không thay cho \`requires\` hoặc \`exports\`; classpath và module path cũng không tương đương. Ví dụ phần 3 là ứng dụng đơn giản chạy trên classpath, không có \`module-info.java\`.

## 8. Chẩn đoán lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra/sửa |
|---|---|---|
| \`cannot find symbol: class Book\` | Thiếu tệp nguồn khi biên dịch, sai package/tên lớp hoặc thiếu compile classpath/sourcepath | Xác nhận khai báo \`package\`, vị trí \`Book.java\`, rồi biên dịch đủ nguồn hoặc chỉ định \`-sourcepath\`. |
| \`package vn.lesson.domain does not exist\` | Trình biên dịch không tìm thấy package trong đường dẫn nguồn/lớp | Đặt đúng source root, truyền tệp phụ thuộc hoặc classpath phù hợp. |
| \`class Book is public, should be declared in a file named Book.java\` | Tên tệp lệch tên kiểu top-level \`public\` | Đổi đúng \`Book.java\`; kiểm tra chữ hoa/thường. |
| \`Book is not public ... cannot be accessed from outside package\` | Top-level class thiếu \`public\` | Chỉnh mức truy cập theo API mong muốn, không cố khắc phục bằng \`import\`. |
| \`has private access\` | Đọc trực tiếp trường/phương thức \`private\` của lớp khác | Dùng API truy cập hợp lệ như \`book.author()\`, hoặc thiết kế lại hợp đồng. |
| \`Could not find or load main class vn.lesson.app.Main\` | Runtime classpath sai gốc, sai tên lớp đầy đủ hoặc chưa biên dịch | Kiểm tra \`out/vn/lesson/app/Main.class\`, chạy \`java -cp out vn.lesson.app.Main\`. |
| \`NoClassDefFoundError\` | Lúc chạy thiếu lớp vốn có lúc biên dịch, hoặc lỗi khi khởi tạo lớp | Kiểm tra runtime classpath/module path và nguyên nhân gốc trong stack trace. |
| \`NoSuchMethodError\` | Bytecode gọi API không khớp phiên bản class/JAR được nạp lúc chạy | Làm sạch đầu ra build, biên dịch và chạy với cùng bộ dependency/version. |
| \`StackOverflowError\` | Hai đối tượng gọi phương thức/constructor qua lại không có điểm dừng | Theo stack trace tìm chuỗi lời gọi lặp; thay đổi cách tạo/nối hoặc điều kiện dừng. |
| \`illegal character: '\uFEFF'\` tại đầu tệp | Tệp được lưu UTF-8 có BOM mà \`javac\` xử lý như ký tự nguồn | Lưu lại mã nguồn UTF-8 không BOM; vẫn dùng \`-encoding UTF-8\`. |

**Trình tự điều tra hiệu quả:** đọc lỗi đầu tiên của \`javac\` → xác định kiểu/tên đang thiếu → mở đúng tệp khai báo → so \`package\`, tên tệp và mức truy cập → kiểm tra source root, compile classpath → biên dịch lại → nếu chỉ lỗi khi chạy, kiểm tra runtime classpath và bytecode/JAR. Đừng sửa \`import\` một cách mò mẫm khi nguyên nhân là đường dẫn tìm lớp.

## 9. Thực hành và kiểm tra hiểu

Thử mở rộng ví dụ chạy:

1. Tạo \`src/vn/lesson/domain/Publisher.java\` với \`public final class Publisher\`, một trường \`name\` và getter. Cho \`Book\` tham chiếu \`Publisher\`; sau đó cập nhật \`Main\`, \`BookCatalog\` và lệnh biên dịch để hiển thị cả nhà xuất bản.
2. Di chuyển \`BookCatalog\` sang package \`vn.lesson.app\`, sửa dòng \`package\`, đường dẫn tệp và \`import\` tương ứng. Dự đoán lỗi nếu chỉ đổi thư mục mà quên sửa \`package\`.
3. Thử xóa \`public\` ở khai báo \`Book\`: tại sao \`Author\` cùng package vẫn dùng được nhưng \`Main\` và \`BookCatalog\` khác package không còn truy cập được?
4. Thử gọi \`javac\` chỉ với \`Main.java\` từ một thư mục đầu ra trống khi **không** chỉ định \`-sourcepath src\`, rồi thêm tùy chọn đó và so sánh kết quả.
5. Thử thay \`Author.feature(Book)\` thành phương thức gọi ngược \`book.author().feature(book)\` vô điều kiện. Nhận diện vì sao hình thành đệ quy lúc chạy dù mã biên dịch hợp lệ; khôi phục bản gốc sau thử nghiệm.

**Tự kiểm tra:** bạn có giải thích được vì sao \`Author.java\` và \`Book.java\` có thể cùng tham chiếu kiểu của nhau, trong khi vòng \`extends\` hay vòng \`requires\` lại không hợp lệ? Bạn có phân biệt được \`-d\`, \`-sourcepath\` và \`-cp\`? Bạn có dự đoán được vị trí \`.class\` và lệnh \`java\` theo package không?

## 10. Checklist trước khi hoàn tất một dự án nhiều tệp

- Mỗi tệp Java có tên, khai báo \`package\` và vị trí tương ứng; các kiểu top-level \`public\` đúng quy tắc đặt tên.
- Các tham chiếu xuyên package dùng \`import\`/tên đầy đủ đúng, và API thực sự có quyền truy cập cần thiết.
- Tất cả nguồn và JAR phụ thuộc hiện diện trên sourcepath/classpath/module path thích hợp cho từng giai đoạn.
- Biên dịch vào thư mục đầu ra riêng, chạy bằng **tên lớp đầy đủ** trên runtime classpath thích hợp.
- Không tạo vòng constructor, đệ quy hoặc khởi tạo tĩnh vô điều kiện chỉ vì các kiểu có quan hệ hai chiều.
- Với dự án lớn, để build tool quản lý dependency, biên dịch tăng dần và kiểm thử; giữ hướng phụ thuộc giữa tầng/module rõ ràng.

Kết quả mong đợi là một đồ thị các kiểu có quan hệ rõ, dễ truy dấu từ \`Main\` đến các lớp phụ thuộc, và một quy trình biên dịch có thể lặp lại trên máy khác.