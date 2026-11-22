# Javadoc mô-đun: Trang tổng quan mô-đun và quan hệ phụ thuộc (Java 9+)

## 1. Vì sao Javadoc cần một trang cho từng mô-đun?

Từ Java 9, **Hệ thống mô-đun Java (Java Platform Module System, JPMS)** cho phép một ứng dụng hoặc thư viện chia mã thành các **named module**. Mỗi mô-đun khai báo tên, những mô-đun cần đọc, gói công khai cho bên ngoài và các quan hệ dịch vụ trong tệp `module-info.java`.

Trước khi đọc một lớp cụ thể, người sử dụng thư viện thường cần trả lời những câu hỏi lớn hơn:

- Mô-đun này giải quyết vấn đề gì?
- Nó công khai những package nào và vì sao?
- Để sử dụng nó cần những mô-đun khác nào?
- Nếu một thư viện công khai kiểu của thư viện thứ hai trong API, người dùng có thể đọc thư viện thứ hai nhờ quan hệ phụ thuộc bắc cầu không?
- Mô-đun cung cấp hoặc sử dụng dịch vụ nào qua cơ chế `ServiceLoader`?

**Trang tổng quan mô-đun (module summary page)** trong Javadoc giúp trả lời các câu hỏi đó. Với Standard Doclet hiện đại, tài liệu API gồm **trang Overview của toàn bộ bộ tài liệu** và **trang riêng cho từng mô-đun**; từ đó người đọc đi tiếp tới package, class/interface và các thành viên API.

Mô hình điều hướng:

```text
docs/index.html                ← trang tổng quan bộ tài liệu
  |
  +── tutorial.model/module-summary.html
  |       +── packages được xuất
  |       +── mô tả module-info.java
  |
  +── tutorial.service/module-summary.html
  |       +── packages được xuất
  |       +── requires transitive tutorial.model
  |       +── đồ thị mô-đun (nếu Javadoc sinh/hiển thị)
  |
  +── tutorial.app/module-summary.html
          +── requires tutorial.service
          +── các phần khác tùy phạm vi tài liệu
```

Javadoc **không tự sửa cấu trúc mô-đun**. Nó đọc mô tả và mã nguồn rồi tạo trang giải thích. Các cạnh phụ thuộc và quyền truy cập thực tế do JPMS, trình biên dịch và trình chạy Java quyết định.

## 2. Một trang Overview và một trang Module có gì khác nhau?

### Overview: điểm vào cho cả bộ tài liệu

Trang gốc thường là `index.html`. Khi tài liệu chứa nhiều named module, nó liệt kê các mô-đun đã được đưa vào quá trình tạo tài liệu cùng phần mô tả tóm tắt. Đây là nơi người đọc tìm đúng thư viện trước khi xem chi tiết.

Một bộ Javadoc cũng có ô **Search**, mục **Index**, liên kết tới **All Packages** và **All Classes and Interfaces**; giao diện cụ thể có thể thay đổi theo bản JDK và bộ doclet.

### Module summary: một trang cho từng mô-đun

Ví dụ: `tutorial.service/module-summary.html`. Trang này có thể chứa:

| Thành phần | Người đọc tìm được gì? |
|---|---|
| Tên mô-đun | Định danh JPMS, ví dụ `tutorial.service` |
| Phần mô tả | Giới thiệu và hướng dẫn lấy từ Javadoc comment đặt trước khai báo `module` |
| Packages | Những package được công khai và các nhóm package khác theo tùy chọn sinh tài liệu |
| Modules | Phụ thuộc khai báo bằng `requires`, bao gồm các modifier như `transitive` hoặc `static` nếu thuộc phạm vi hiển thị |
| Services | Các dịch vụ được mô-đun sử dụng (`uses`) hoặc triển khai (`provides ... with`) |
| Module Graph | Minh họa quan hệ mô-đun khi bộ tài liệu/Standard Doclet có mục biểu đồ này |
| Liên kết API | Điều hướng sang tài liệu package, type và các mô-đun liên quan đã được liên kết |

**Lưu ý quan trọng:** Một bảng/mục không nhất thiết xuất hiện trên mọi trang. Điều này phụ thuộc nội dung `module-info.java`, số mô-đun được đưa vào bộ tài liệu, tùy chọn `javadoc` và bản doclet. Ví dụ, mô-đun không khai báo dịch vụ sẽ không có danh sách dịch vụ đáng kể; một package nội bộ cũng có thể bị ẩn trong tài liệu API công khai theo mặc định.

Trong Javadoc của chính JDK, bạn có thể xem những ví dụ thực tế như:

- [Trang Overview của Java SE/JDK](https://docs.oracle.com/en/java/javase/26/docs/api/)
- [Trang mô-đun `java.sql`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/module-summary.html)
- [Trang mô-đun `jdk.javadoc`](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.javadoc/module-summary.html)

Các ví dụ này thể hiện mô tả, package, quan hệ requires và bảng services tùy từng mô-đun.

## 3. Nguồn của trang mô-đun là module-info.java và Javadoc comment

Một mô-đun thông thường có tệp `module-info.java` ở gốc cây mã nguồn của mô-đun. Ví dụ:

```java
/**
 * Mô-đun cung cấp dịch vụ chào hỏi.
 *
 * <p>API của mô-đun nhận đối tượng người học từ
 * {@code tutorial.model} và trả chuỗi lời chào.
 *
 * <p>Ứng dụng chỉ cần khai báo phụ thuộc vào mô-đun này
 * để sử dụng API dịch vụ và các kiểu mô hình được xuất.
 */
module tutorial.service {
    requires transitive tutorial.model;
    exports tutorial.service.api;
}
```

Đây là **nội dung hoàn chỉnh của một tệp `module-info.java`**, với điều kiện mô-đun `tutorial.model` tồn tại và package `tutorial.service.api` có mã nguồn. Javadoc comment `/** ... */` phải nằm **ngay trước khai báo mô-đun** để mô tả ấy xuất hiện ở trang tổng quan.

Trong đoạn trên:

- Dòng đầu của Javadoc comment là tóm tắt ngắn, hữu ích để hiển thị trong danh sách mô-đun.
- Những đoạn tiếp theo giải thích mục đích, phạm vi sử dụng và quan hệ giữa các mô-đun; đó là thông tin mà riêng biểu đồ phụ thuộc khó truyền tải.
- `requires transitive tutorial.model;` là khai báo phụ thuộc bắc cầu (giải thích ở mục 4).
- `exports tutorial.service.api;` cho phép mô-đun khác truy cập các kiểu `public` thuộc package đó, nếu mô-đun sử dụng có quan hệ đọc phù hợp.

**Mẹo biên soạn:** Mở đầu comment mô-đun bằng “mô-đun làm gì và người dùng nhận được API gì”, rồi mới giải thích cách dùng và giới hạn phụ thuộc. Chỉ lặp lại `requires`/`exports` dưới dạng danh sách thô sẽ không giúp người đọc hiểu thiết kế.

Đối với từng package, có thể viết comment riêng trong `package-info.java`; với class/interface, viết Javadoc trên các khai báo của chúng. Ba cấp tài liệu bổ sung cho nhau:

```text
module-info.java  → Tổng quan mô-đun, biên giới API và phụ thuộc
package-info.java → Mục tiêu, quy ước và khái niệm của package
Class.java        → Hợp đồng của class, method, constructor, field
```

## 4. Đọc quan hệ phụ thuộc cho đúng: requires, transitive, static và exports

Quan hệ trên trang mô-đun phản ánh **khai báo và đồ thị đọc (readability graph)** của JPMS. Cần phân biệt mối phụ thuộc và khả năng truy cập package.

| Khai báo | Ý nghĩa hiện hành | Cách đọc trên tài liệu |
|---|---|---|
| `requires B;` | Mô-đun hiện tại đọc mô-đun `B` | Phụ thuộc trực tiếp |
| `requires transitive B;` | Mô-đun hiện tại đọc `B`; các mô-đun đọc nó còn được đọc `B` theo quy tắc bắc cầu | Phụ thuộc bắc cầu, thường cần khi API công khai dùng kiểu từ `B` |
| `requires static B;` | Cần `B` khi biên dịch, nhưng có thể vắng mặt ở runtime nếu không được resolve bởi đường khác | Phụ thuộc tùy chọn lúc chạy |
| `exports p;` | Công khai các kiểu `public` trong package `p` cho các mô-đun đọc được mô-đun hiện tại | Biên giới API công khai |
| `exports p to B;` | Chỉ xuất package `p` cho mô-đun được chỉ định | Xuất có giới hạn, không phải API công khai đại trà |
| `opens p;` | Cho phép truy cập phản chiếu sâu vào package `p` theo quy tắc JPMS | Phục vụ reflection; **không thay `exports`** để dùng kiểu ở compile time |
| `uses Service;` | Khai báo mô-đun sử dụng một dịch vụ | Quan hệ dịch vụ |
| `provides Service with Impl;` | Khai báo triển khai dịch vụ | Quan hệ nhà cung cấp dịch vụ |

Ở bảng trên, `B` và `p` là tên minh họa, không phải literal đặc biệt.

### requires khác exports như thế nào?

Để mã ở mô-đun A tham chiếu tới kiểu `public tutorial.model.api.Person` của mô-đun B, thông thường cần **đồng thời**:

1. A **đọc được** B (trực tiếp hoặc nhờ `requires transitive`).
2. B **xuất package chứa kiểu** cho A.
3. Kiểu/những thành viên được dùng có mức truy cập Java phù hợp (ví dụ `public`).

Chỉ có mũi tên `requires` không đồng nghĩa mọi package của thư viện phụ thuộc đều được truy cập. Các package không được xuất vẫn được đóng gói ở cấp mô-đun.

### requires transitive và phụ thuộc gián tiếp

Giả sử:

```text
tutorial.app
     │ requires
     ▼
tutorial.service
     │ requires transitive
     ▼
tutorial.model
     └── exports tutorial.model.api
```

- `tutorial.service` đọc trực tiếp `tutorial.model`.
- `tutorial.app` khai báo **chỉ** `requires tutorial.service;`.
- Do `tutorial.service` dùng `requires transitive tutorial.model;`, mô-đun `tutorial.app` cũng **đọc được** `tutorial.model`.
- Vì `tutorial.model` xuất `tutorial.model.api`, mã trong `tutorial.app` có thể sử dụng kiểu `Person` ở package này mà không cần thêm dòng `requires tutorial.model;`.

Đồ thị đọc sau khi áp dụng quy tắc bắc cầu có nhiều cạnh hơn các khai báo `requires` trực tiếp. Trang module có thể trình bày danh sách “Requires”, “Indirect Exports”, hoặc Module Graph theo cách khác nhau; **mỗi nhãn phải được hiểu trong ngữ cảnh JPMS**, không suy đoán từ hình vẽ rằng toàn bộ package của một dependency được công khai.

Ngoài các quan hệ khai báo, mọi named module đều phụ thuộc cơ sở vào `java.base` (thông thường không cần viết `requires java.base;`). Những chi tiết nền tảng này có thể xuất hiện khác nhau trong công cụ phân tích hoặc biểu đồ.

## 5. Ví dụ ba mô-đun Java 17+ có thể biên dịch và chạy

Ví dụ này tạo ba mô-đun độc lập để minh họa rõ cả **trang tổng quan Javadoc** lẫn **mối phụ thuộc bắc cầu khi biên dịch**:

- `tutorial.model` định nghĩa một kiểu dữ liệu công khai.
- `tutorial.service` cung cấp một hàm dùng kiểu đó trong API công khai.
- `tutorial.app` sử dụng cả hai API nhưng chỉ khai báo `requires tutorial.service`.

### Cấu trúc thư mục

Tạo cấu trúc sau; tên thư mục mô-đun ở tầng đầu phải khớp tên trong `module-info.java`:

```text
demo/
└── src/
    ├── tutorial.model/
    │   ├── module-info.java
    │   └── tutorial/model/api/Person.java
    ├── tutorial.service/
    │   ├── module-info.java
    │   └── tutorial/service/api/Greetings.java
    └── tutorial.app/
        ├── module-info.java
        └── tutorial/app/Main.java
```

### Mô-đun 1: tutorial.model

**`src/tutorial.model/module-info.java`**

```java
/**
 * Cung cấp các kiểu dữ liệu dùng chung cho ứng dụng minh họa.
 *
 * <p>Package công khai chứa bản ghi Person của người học.
 */
module tutorial.model {
    exports tutorial.model.api;
}
```

**`src/tutorial.model/tutorial/model/api/Person.java`**

```java
package tutorial.model.api;

/**
 * Thông tin tối thiểu của một người học.
 *
 * @param name tên hiển thị của người học
 */
public record Person(String name) {}
```

Từ khóa `record` là tính năng Java hiện hành; để thống nhất với ví dụ, hãy dùng JDK 17 trở lên.

### Mô-đun 2: tutorial.service

**`src/tutorial.service/module-info.java`**

```java
/**
 * Cung cấp dịch vụ tạo lời chào cho người học.
 *
 * <p>API công khai sử dụng kiểu Person từ tutorial.model,
 * vì vậy quan hệ requires transitive cho phép module sử dụng
 * dịch vụ đồng thời tham chiếu kiểu Person.
 */
module tutorial.service {
    requires transitive tutorial.model;
    exports tutorial.service.api;
}
```

**`src/tutorial.service/tutorial/service/api/Greetings.java`**

```java
package tutorial.service.api;

import tutorial.model.api.Person;

/** Tạo lời chào đơn giản. */
public final class Greetings {

    private Greetings() {}

    /**
     * Trả lời chào cho một người học.
     *
     * @param person người nhận lời chào
     * @return lời chào theo tên người học
     */
    public static String hello(Person person) {
        return "Hello, " + person.name();
    }
}
```

Ở đây `Person` xuất hiện trong **chữ ký public của `hello(Person)`**. Điều này làm cho `requires transitive tutorial.model` trở thành một quyết định API dễ hiểu: mã sử dụng `tutorial.service` thường cũng cần truy cập kiểu `Person`.

### Mô-đun 3: tutorial.app

**`src/tutorial.app/module-info.java`**

```java
/**
 * Ứng dụng minh họa lời chào và cách đọc quan hệ module.
 */
module tutorial.app {
    requires tutorial.service;
}
```

**`src/tutorial.app/tutorial/app/Main.java`**

```java
package tutorial.app;

import tutorial.model.api.Person;
import tutorial.service.api.Greetings;

/** Điểm bắt đầu chương trình. */
public final class Main {

    private Main() {}

    public static void main(String[] args) {
        System.out.println(Greetings.hello(new Person("Lan")));
    }
}
```

**Điểm cần quan sát:** `Main` import `Person` từ `tutorial.model.api`, nhưng `module-info.java` của `tutorial.app` **không khai báo requires trực tiếp tới `tutorial.model`**. Điều này hợp lệ do `requires transitive` ở `tutorial.service` và `exports` ở `tutorial.model`.

### Biên dịch và chạy

Chạy từ thư mục `demo/`, nơi có thư mục `src/` như cấu trúc trên:

```bash
javac --release 17 -encoding UTF-8 \
  --module-source-path src \
  -d out \
  --module tutorial.model,tutorial.service,tutorial.app

java --module-path out \
  --module tutorial.app/tutorial.app.Main
```

Các dấu `\` cuối dòng là **cách nối lệnh cho Bash trên Linux/macOS**. Trên Windows PowerShell, hãy chạy dạng **một dòng** tương đương:

```powershell
javac --release 17 -encoding UTF-8 --module-source-path src -d out --module tutorial.model,tutorial.service,tutorial.app
java --module-path out --module tutorial.app/tutorial.app.Main
```

**Stdout dự kiến, dựa trên mã ví dụ:**

```text
Hello, Lan
```

Chương trình không dùng thư viện ngoài hoặc I/O mạng; kết quả chỉ dựa vào bản ghi `Person` và hàm `Greetings.hello`. Nếu thiếu `requires transitive` ở mô-đun dịch vụ, mô-đun ứng dụng không còn được đọc `tutorial.model` qua tuyến phụ thuộc này, và ví dụ sẽ không biên dịch khi `Main` trực tiếp tham chiếu `Person`.

## 6. Sinh Javadoc và xem trang tổng quan mô-đun

Vẫn từ thư mục `demo/`, chạy:

```bash
javadoc -encoding UTF-8 -d docs \
  --module-source-path src \
  --module tutorial.model,tutorial.service,tutorial.app \
  --show-module-contents all \
  --show-packages all
```

Windows PowerShell có thể dùng **một dòng**:

```powershell
javadoc -encoding UTF-8 -d docs --module-source-path src --module tutorial.model,tutorial.service,tutorial.app --show-module-contents all --show-packages all
```

Ý nghĩa của lệnh:

- `--module-source-path src`: nơi tìm các cây mã nguồn của mô-đun; trong ví dụ, từng thư mục con `tutorial.*` chứa một `module-info.java`.
- `--module ...`: tên **ba mô-đun được yêu cầu tạo tài liệu**. Đây là danh sách cách nhau bằng dấu phẩy, không phải đường dẫn file.
- `-d docs`: thư mục đầu ra của HTML.
- `-encoding UTF-8`: giải mã chú thích Javadoc tiếng Việt một cách nhất quán.
- `--show-module-contents all`: yêu cầu mức mô tả chi tiết của module declaration.
- `--show-packages all`: bao gồm các package không được xuất trong phạm vi tài liệu tạo ra, hữu ích để xem cả package `tutorial.app` trong bản demo. Với **tài liệu API công khai**, thường nên giới hạn package về mức được xuất để tránh công bố cấu trúc nội bộ.

Sau khi hoàn thành, các trang đáng xem gồm:

```text
docs/
├── index.html
├── tutorial.model/
│   └── module-summary.html
├── tutorial.service/
│   └── module-summary.html
└── tutorial.app/
    └── module-summary.html
```

Đây là **các đường dẫn tiêu biểu** của Standard Doclet; thực tế có thêm file CSS, JavaScript, chỉ mục, tài liệu package, class và các tệp hỗ trợ khác.

Mở `docs/index.html` trong trình duyệt rồi chọn mô-đun `tutorial.service`. Trên trang tổng quan của nó, đọc mô tả, danh sách package và quan hệ `requires transitive tutorial.model`. Chọn tiếp `tutorial.model` để thấy package `tutorial.model.api` và kiểu `Person`.

**Không cần đi từ index mới xem được:** khi bạn đã biết tên module, có thể mở trực tiếp `docs/tutorial.service/module-summary.html`. Việc liên kết qua lại sẽ đầy đủ nhất khi các mô-đun cần tham chiếu đều nằm trong tập đã sinh tài liệu hoặc được nối tới một bộ tài liệu ngoài.

### Vì sao không thấy package Main ở API mặc định?

`tutorial.app` **không `exports tutorial.app;`**, vì ứng dụng không định cung cấp public API cho các mô-đun khác. Javadoc ở chế độ công khai thường tập trung vào package được xuất. Lựa chọn `--show-packages all` của ví dụ này là để bạn vẫn quan sát được các package nội bộ khi học, không phải gợi ý thêm `exports` chỉ để chúng hiện trên website tài liệu.

## 7. Cách đọc mô-đun nào phụ thuộc mô-đun nào

Với mô hình ba mô-đun, có hai cách biểu diễn cần phân biệt:

**Khai báo trực tiếp trong module-info.java**

```text
tutorial.app     --requires----------> tutorial.service
tutorial.service --requires transitive--> tutorial.model
tutorial.model   --exports-----------> tutorial.model.api
```

Mũi tên `exports` **không phải phụ thuộc mô-đun**: nó mô tả một package thuộc mô-đun được công khai. Do đó nên vẽ riêng quan hệ xuất package khi mô tả kiến trúc.

**Quan hệ đọc được suy ra bởi JPMS**

```text
tutorial.app
    ├── đọc tutorial.service (requires trực tiếp)
    └── đọc tutorial.model   (bắc cầu qua tutorial.service)

tutorial.service
    └── đọc tutorial.model   (requires transitive trực tiếp)
```

Hai góc nhìn phục vụ hai câu hỏi khác nhau:

- *Mã nguồn của mô-đun khai báo những phụ thuộc nào?* → Xem các dòng `requires` trong `module-info.java` và bảng requires.
- *Ứng dụng có thể tham chiếu API của mô-đun nào?* → Xem **đồ thị đọc sau quy tắc bắc cầu**, đồng thời kiểm tra `exports` của các package.

Nếu trang Javadoc có mục **Module Graph**, dùng biểu đồ để điều hướng nhanh, sau đó kiểm tra bảng “Modules” và định nghĩa JPMS để xác nhận quan hệ. Biểu đồ không phải bảng cấu hình runtime và không chứng minh các module tùy chọn đều có mặt trong lần chạy thật.

### Phụ thuộc gián tiếp không đồng nghĩa với “tất cả module con”

Ví dụ `tutorial.service` có thêm `requires java.logging;` nhưng không `transitive`: mô-đun `tutorial.app` **không tự động được đọc `java.logging` chỉ vì nó đọc `tutorial.service`**. Khi API công khai không cần kiểu của `java.logging`, phụ thuộc bình thường thường thích hợp hơn.

Với `requires static`, mô-đun có thể cần được cung cấp khi biên dịch nhưng không phải luôn hiện diện ở runtime. Không được nhìn bản Javadoc chứa tên dependency rồi suy ra nó đã được resolve trong mọi tiến trình.

## 8. Các tùy chọn javadoc liên quan đến đồ thị và nội dung module

| Tùy chọn hiện hành | Khi nào dùng | Điều cần tránh hiểu nhầm |
|---|---|---|
| `--module m1,m2` | Chọn những named module cần sinh tài liệu | Không có nghĩa “đọc toàn bộ module path và tự xuất hết” |
| `--module-source-path path` | Cung cấp cây nguồn của một hoặc nhiều module | Phải khớp cách tổ chức thư mục/source layout |
| `--module-path path` | Giúp tìm các module đã biên dịch mà tài liệu nguồn phụ thuộc | Không tự chuyển mọi JAR ở path thành trang module |
| `--expand-requires transitive` | Mở rộng **tập module được tạo tài liệu** theo các phụ thuộc bắc cầu | Không làm thay đổi quan hệ `requires` trong mã |
| `--expand-requires all` | Mở rộng tập module tài liệu theo mọi phụ thuộc | Có thể kéo vào một tập module rất lớn, kể cả module JDK |
| `--show-module-contents api` | Mô tả module ở mức API | Có thể ẩn thông tin khai báo chỉ phục vụ triển khai |
| `--show-module-contents all` | Mô tả chi tiết hơn toàn bộ khai báo module | Chế độ dành cho tài liệu nội bộ/khảo sát kiến trúc |
| `--show-packages exported` | Tập trung những package được xuất | Không liệt kê mọi package private/nội bộ |
| `--show-packages all` | Xem cả package không được xuất | Không đồng nghĩa package ấy trở thành truy cập được bên ngoài |
| `-d directory` | Chỉ định thư mục xuất tài liệu | Không ảnh hưởng đồ thị phụ thuộc |
| `-encoding UTF-8` | Đọc nội dung Javadoc comment bằng UTF-8 | Khác với `-docencoding` điều khiển dữ liệu xuất |
| `--release 17` | Phân tích theo API/ngữ pháp bản phát hành hỗ trợ | Không thay đổi yêu cầu hệ thống module thực tế |
| `-link URL` | Liên kết tới tài liệu API ngoài có thể truy cập | Không thêm module vào bản build hay module graph runtime |

**Quan trọng với `--expand-requires`:** Đây là **bộ lọc phạm vi xuất tài liệu**, khác với logic độ đọc bắc cầu của `requires transitive`. Một trang module vẫn có thể ghi tên một module nó phụ thuộc dù bạn không sinh trang HTML đầy đủ cho module đó. Nếu cần trang của thư viện phụ thuộc trong cùng bộ, hãy đưa nó vào danh sách `--module` hoặc chủ động mở rộng khi phù hợp.

Ở dự án Gradle/Maven nhiều module, hệ thống build thường cung cấp source path và module path; nên xem cấu hình plugin sinh Javadoc của dự án thay vì áp dụng máy móc lệnh demo vào một thư mục nguồn khác cấu trúc.

## 9. Services và các quan hệ không phải requires

Một trang tổng quan mô-đun có thể có bảng **Services** khi `module-info.java` khai báo:

```java
module tutorial.consumer {
    requires tutorial.spi;
    uses tutorial.spi.Codec;
}
```

Đây là **mảnh minh họa**, giả định module `tutorial.spi` xuất package chứa interface `Codec`; chưa đủ mã nguồn để biên dịch riêng. Một provider có thể viết:

```java
module tutorial.codec.json {
    requires tutorial.spi;
    provides tutorial.spi.Codec
        with tutorial.codec.json.JsonCodec;
}
```

Cũng là **mảnh minh họa**; class `JsonCodec` phải thật sự tồn tại và thỏa hợp đồng provider.

- `uses` tuyên bố mô-đun sử dụng một dịch vụ.
- `provides ... with` tuyên bố mô-đun cung cấp một triển khai dịch vụ.
- Đây là thông tin giúp đọc hệ sinh thái module, nhưng quan hệ cung cấp dịch vụ **không giống một cạnh `requires`** thông thường.
- Việc module provider có được resolve và service được phát hiện lúc chạy còn phụ thuộc cấu hình, đường dẫn module và cách chương trình dùng `ServiceLoader`.

Khi viết Javadoc cấp module, có thể dùng các thẻ `@uses` và `@provides` để bổ sung mô tả phục vụ bảng dịch vụ. Nếu muốn ghi rõ cách dùng trong trang tổng quan, hãy giải thích các dịch vụ đó giải quyết nhu cầu gì, thay vì chỉ lặp lại tên interface.

## 10. Xác minh kiến trúc ngoài giao diện Javadoc

Javadoc trả lời câu hỏi **API được mô tả như thế nào**. Để kiểm tra module thực sự được khai báo và phân tích phụ thuộc biên dịch, có thể dùng các công cụ đi kèm JDK hiện đại:

### java --describe-module

Sau khi tạo thư mục `out/` từ lệnh `javac` ở mục 5:

```bash
java --module-path out --describe-module tutorial.service
```

Lệnh này mô tả module đã biên dịch, gồm tên và các directive liên quan. Nó giúp đối chiếu những gì nằm trong `module-info.class` với thông tin Javadoc lấy từ `module-info.java`. Kết quả có thể có thứ tự dòng khác nhau theo JDK, nên không nên viết một bản stdout cố định giả định mọi trình chạy giống hệt nhau.

### jdeps cho phân tích phụ thuộc

`jdeps` xem phụ thuộc của class/JAR/module đã biên dịch. Ví dụ:

```bash
jdeps --module-path out --module tutorial.app --list-deps
```

Lệnh này giúp phân tích dependency từ bytecode và module descriptor. Nó phục vụ việc kiểm tra kiến trúc; không thay thế comment về ý nghĩa API trong trang Javadoc. Đối với các module phức tạp, có thể xem thêm `jdeps --check` hoặc các lựa chọn xuất đồ thị theo hướng dẫn hiện hành của chính JDK.

**Đừng lẫn ba khái niệm:**

1. Javadoc module summary: diễn giải giao diện công khai, khai báo module, quan hệ và tài liệu do tác giả viết.
2. Module descriptor: các ràng buộc JPMS trong `module-info.class`.
3. Runtime resolution: tập module thực sự được chọn/resolve khi chạy, có thể chịu ảnh hưởng của module path, root module, `requires static` và cơ chế service binding.

Trang tài liệu tốt giúp hiểu thiết kế, nhưng vẫn cần compile/run và kiểm tra module path của môi trường triển khai.

## 11. Những lỗi thường gặp khi viết hoặc đọc tài liệu module

| Hiện tượng | Nguyên nhân | Cách sửa |
|---|---|---|
| Chạy javadoc xong chỉ thấy trang class/package, không có trang cho module mong đợi | Chạy theo mô hình package truyền thống hoặc không chọn named module nguồn phù hợp | Bảo đảm có `module-info.java`, `--module-source-path` và `--module` phù hợp |
| Trang mô-đun ít mô tả, chỉ thấy các bảng | Thiếu Javadoc comment trước `module` | Viết phần mô tả module bằng `/** ... */` ở `module-info.java` |
| Module phụ thuộc được nêu nhưng không có trang chi tiết | Dependency không thuộc tập module được tạo tài liệu | Thêm vào `--module`, mở rộng phạm vi hoặc liên kết tài liệu ngoài |
| Package tồn tại trong source nhưng không xuất hiện ở tài liệu API | Package không được `exports` và tùy chọn chỉ lấy package công khai | Khi tài liệu nội bộ cần xem thêm, dùng `--show-packages all`; không tự ý thêm `exports` |
| Xem biểu đồ rồi tưởng mọi class của dependency đều truy cập được | Nhầm `requires` với `exports` | Kiểm tra cả quan hệ đọc và package đã được xuất |
| Ghi `requires` thay `requires transitive` trong thư viện công khai kiểu của module khác | Client thiếu quan hệ đọc gián tiếp tới kiểu được đưa vào API | Cân nhắc `requires transitive` cho dependency thực sự thuộc hợp đồng public |
| Tưởng `--expand-requires all` thay đổi runtime | Tùy chọn chỉ thay đổi tập module được Javadoc xuất | Kiểm tra runtime bằng `java`, compiler và cấu hình module path |
| Ghi toàn bộ package nội bộ vào trang API công khai | Dùng `--show-packages all` không cân nhắc phạm vi phát hành | Tách tài liệu nội bộ và tài liệu API public theo nhu cầu |
| Comment nhắc module đã đổi tên | Mô tả viết tay không được đồng bộ với `module-info.java` | Khi đổi cấu trúc phụ thuộc, cập nhật comment và sinh Javadoc lại |
| Ví dụ `java --module-path ...` không chạy | Sai đường dẫn, thiếu module hoặc nhầm tên module/tên class | Kiểm tra `out/`, khai báo module và lệnh `java --module ...` |
| Dấu tiếng Việt bị sai | Charset đọc source không khớp | Lưu nguồn UTF-8 và truyền `-encoding UTF-8` |
| Dựa vào Javadoc để biết phiên bản dependency thật của Maven/Gradle | Javadoc chủ yếu mô tả module name và khai báo, không thay dependency lock/metadata build | Đối chiếu thêm cấu hình build, cây dependency và bản artifact được dùng |

### Checklist trước khi phát hành tài liệu Javadoc

1. **Mục đích mô-đun rõ trong một câu đầu tiên:** người đọc nhìn bảng Overview biết chọn module nào.
2. **Trang module giải thích phạm vi trách nhiệm:** có ngữ cảnh kiến trúc, cách dùng, các ranh giới.
3. **Quan hệ `requires` đúng:** chỉ dùng `requires transitive` khi muốn bộc lộ dependency cho các module dùng API.
4. **Package được xuất hợp lý:** API public tập trung ở những package có hợp đồng ổn định.
5. **Comment và khai báo nhất quán:** tên class, module, package, thẻ link, cấu hình service đều còn tồn tại.
6. **Lệnh javadoc phù hợp:** phân biệt tài liệu API công khai với tài liệu nội bộ.
7. **Trang HTML đã mở kiểm tra:** ít nhất xem index, module summary, packages, liên kết tới các dependency, và kiểm tra cảnh báo Javadoc.
8. **Ví dụ biên dịch:** nếu Javadoc minh họa lệnh chạy như bài này, compile và run trên JDK phù hợp để tránh lỗi tên module.

## 12. Tự kiểm tra kiến thức

1. **Trang `index.html` và `module-summary.html` khác gì?** `index.html` là điểm vào của bộ tài liệu; mỗi `module-summary.html` mô tả một mô-đun cụ thể cùng package, dependency, service và phần giới thiệu của mô-đun ấy.
2. **Muốn phần giới thiệu xuất hiện trên trang module thì viết ở đâu?** Trong Javadoc comment đặt ngay trước khai báo `module` ở `module-info.java`.
3. **Nếu `app requires service` và `service requires transitive model` thì app có đọc được model không?** Có, theo quy tắc phụ thuộc bắc cầu của JPMS.
4. **App đọc được model thì tự động sử dụng được mọi class bên trong model không?** Không; package chứa class phải được `exports` phù hợp và class phải có mức truy cập đúng.
5. **`--expand-requires all` thay đổi file `module-info.java` không?** Không. Nó mở rộng tập module đưa vào tài liệu.
6. **Tại sao dùng `--show-packages all` không biến package nội bộ thành API public?** Vì quyền truy cập được JPMS quyết định từ `exports`, không từ tùy chọn tạo HTML.
7. **Dùng công cụ nào để đối chiếu khai báo module đã biên dịch?** `java --describe-module`; khi cần phân tích phụ thuộc từ bytecode/JAR dùng `jdeps`.
8. **Tại sao cần comment giải thích mục đích thay vì chỉ sinh đồ thị?** Đồ thị mô tả cạnh phụ thuộc, không truyền tải được lý do thiết kế, đối tượng dùng API và cách tích hợp.

## Tài liệu chính thức còn phù hợp

- [The javadoc Command — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javadoc.html)
- [Javadoc Tool Guide — Java SE 25](https://docs.oracle.com/en/java/javase/25/javadoc/javadoc-tool.html)
- [JavaDoc Help: Overview / Module pages — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/help-doc.html)
- [Java SE 26 API Overview](https://docs.oracle.com/en/java/javase/26/docs/api/)
- [Module java.sql — ví dụ trang tổng quan mô-đun](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/module-summary.html)
- [java.lang.module: Module Resolution — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/module/package-summary.html)
- [The jdeps Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jdeps.html)
