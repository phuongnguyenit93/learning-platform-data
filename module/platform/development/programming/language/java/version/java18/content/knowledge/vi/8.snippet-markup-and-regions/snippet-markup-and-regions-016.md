# Chẩn đoán region thiếu, sai tên, thiếu @end và giới hạn của markup cuối dòng

> **Chương:** Markup và region  
> **Module học:** JAVA_VERSION_JAVA18 — JEP 413 đưa `{@snippet}` và markup comment vào Standard Doclet từ JDK 18. Cú pháp region, cách kiểm tra snippet và các giới hạn của markup cuối dòng vẫn dùng được trên JDK hiện đại.  
> **Mục tiêu:** Đọc đúng lỗi region không tìm thấy, region không được ghép cặp, `@end` thừa hoặc sai tên; biết cách sửa marker và áp dụng markup khi ngôn ngữ snippet không cho phép comment ở cuối dòng.

## 1. Region dùng để làm gì?

Snippet có thể chứa cả một file hoặc một đoạn code. Khi chỉ muốn đưa một phần của file vào Javadoc, ta đánh dấu vùng bằng region. Region cũng xác định phạm vi mà các markup như `@highlight`, `@replace` và `@link` tác động.

Một region có thể:

- **Có tên:** bắt đầu bằng `@start region=tenVung` và kết thúc bằng `@end region=tenVung`.
- **Không có tên:** bắt đầu bằng `@start` hoặc một markup khai báo region; kết thúc bằng `@end`.
- **Lồng nhau:** region bên trong có thể nằm trọn trong region bên ngoài.
- **Chồng lấn:** các vùng có thể giao nhau; khi chồng lấn, nên đặt tên để ghép đúng từng cặp đầu/cuối.

Region không phải cú pháp của Java. Đây là markup comment do Standard Doclet đọc khi xử lý `{@snippet}`. Các comment markup được loại khỏi đoạn code hiển thị trong tài liệu được tạo.

## 2. Phân biệt hai nơi dùng thuộc tính region

Thuộc tính `region` xuất hiện ở hai vị trí với mục đích liên quan nhưng khác nhau.

### 2.1. Chọn vùng được hiển thị trong snippet

Với external snippet, thuộc tính `region` trên tag `{@snippet}` chọn vùng có tên trong file ngoài:

~~~java
{@snippet file=ServerExamples.java region=startServer}
~~~

Trong file `ServerExamples.java`, vùng phải được khai báo bằng cặp marker:

~~~java
public class ServerExamples {
    // @start region=startServer
    HttpServer server = HttpServer.create(address, 0);
    server.createContext("/", handler);
    server.start();
    // @end region=startServer
}
~~~

Khi đó, Javadoc chỉ đưa các dòng nằm trong region `startServer` vào snippet. Các marker `@start` và `@end` không xuất hiện trong phần code được hiển thị.

### 2.2. Xác định phạm vi của markup

Một markup như `@highlight` có thể tự mở region thông qua thuộc tính `region`:

~~~java
{@snippet :
    public void start() { // @highlight region=startFlow substring="server.start()"
        server.start();
    }                     // @end region=startFlow
}
~~~

Ở ví dụ này, `@highlight region=startFlow` vừa bắt đầu một region có tên `startFlow`, vừa yêu cầu highlight nội dung khớp `substring` trong phạm vi đó. `@end region=startFlow` đóng region.

Các markup có thể mở region theo cách này là `@highlight`, `@replace` và `@link`. Vì vậy, nếu một markup đã khai báo `region` thì không cần thêm `@start region` thứ hai cho cùng vùng đó.

## 3. Cú pháp bắt đầu và kết thúc region

Các dạng thường dùng:

| Mục đích | Cú pháp |
| --- | --- |
| Bắt đầu region có tên | `// @start region=main` |
| Kết thúc region có tên | `// @end region=main` |
| Bắt đầu region không tên | `// @start` |
| Kết thúc region không tên gần nhất chưa đóng | `// @end` |
| Mở region bằng highlight | `// @highlight region=main substring="start()"` |
| Mở region bằng replace | `// @replace region=main substring="TODO" replacement="..."` |
| Mở region bằng link | `// @link region=main substring="HttpServer" target="HttpServer"` |

Với `@end` không ghi tên, Standard Doclet đóng region được bắt đầu gần nhất mà chưa có `@end` tương ứng. Đây là cách thuận tiện cho region lồng nhau. Khi các region chồng lấn hoặc khó theo dõi thứ tự, dùng tên ở cả đầu và cuối.

Tên region phải khớp chính xác giữa nơi tham chiếu, marker bắt đầu và marker kết thúc. Khi sửa lỗi, kiểm tra cả chữ hoa/chữ thường, dấu gạch dưới, chính tả và giá trị attribute.

## 4. Chẩn đoán các lỗi region thường gặp

Standard Doclet có thể phát ra thông báo cho các lỗi markup region. Các nhãn chẩn đoán thường gặp gồm:

| Thông báo | Ý nghĩa | Việc cần kiểm tra |
| --- | --- | --- |
| `region not found: "name"` | Snippet yêu cầu một region nhưng nội dung được đọc không có region mang tên đó. | Tên trong `{@snippet ... region=name}`, marker `@start` và đúng file snippet. |
| `no region to end` | Có `@end` nhưng không có region đang mở phù hợp để đóng. | `@end` thừa, marker bắt đầu bị thiếu hoặc tên ở `@end region=...` sai. |
| `unpaired region` | Có region được mở nhưng không có marker kết thúc tương ứng. | Tìm `@start` hoặc markup có `region` chưa có `@end`. |
| `duplicated region` | Có khai báo region trùng lặp hoặc cấu trúc marker gây trùng. | Kiểm tra tên region và các marker bị copy nhầm. |
| `spurious markup` | Markup không có tác dụng hợp lệ trong vị trí/phạm vi đó. | Kiểm tra tên tag, vị trí comment và cú pháp attribute. |

Thông báo cụ thể có thể thay đổi theo bản cập nhật JDK, nhưng ý nghĩa chẩn đoán vẫn giúp khoanh vùng lỗi. Đặc biệt, `region not found` là lỗi **không tìm thấy vùng được yêu cầu**; `unpaired region` là lỗi **vùng đã mở nhưng chưa đóng**; `no region to end` là lỗi **marker đóng không có vùng tương ứng**.

## 5. Lỗi region not found: tên được tham chiếu không tồn tại

Giả sử Javadoc yêu cầu region `startServer`:

~~~java
/**
 * Ví dụ khởi động server.
 *
 * {@snippet file=ServerExamples.java region=startServer}
 */
public class ServerGuide {
}
~~~

Nhưng file snippet lại khai báo tên `serverStart`:

~~~java
public class ServerExamples {
    // @start region=serverStart
    server.start();
    // @end region=serverStart
}
~~~

Hai tên khác nhau nên Standard Doclet không thể tìm region `startServer`. Kết quả có thể là diagnostic dạng `region not found: "startServer"`.

Sửa bằng cách thống nhất tên ở hai nơi:

~~~java
public class ServerExamples {
    // @start region=startServer
    server.start();
    // @end region=startServer
}
~~~

Khi gặp `region not found`, kiểm tra theo thứ tự:

1. Tag `{@snippet}` đang tham chiếu đúng tên chưa?
2. Tên sau `@start region=` có trùng chính xác không?
3. File được tham chiếu có đúng file cần sửa không?
4. External snippet có nằm trong thư mục `snippet-files` của package hoặc trên đường dẫn `--snippet-path` không?
5. Marker có thực sự là markup comment được Standard Doclet nhận diện không?

Nếu file external không tìm thấy, thông báo sẽ nói về file snippet không tìm thấy; đó là lỗi đường dẫn file, khác với lỗi tìm region trong một file đã đọc được.

## 6. Lỗi sai tên ở marker kết thúc

Ví dụ mở region `loadConfig` nhưng lại đóng `loadConfing`:

~~~java
// @start region=loadConfig
Properties properties = new Properties();
properties.load(input);
// @end region=loadConfing
~~~

Tên kết thúc không khớp tên bắt đầu. Doclet không thể ghép `@end region=loadConfing` với `loadConfig`; vùng đã mở cũng không có điểm kết thúc hợp lệ. Tùy cấu trúc và phiên bản JDK, bạn có thể thấy chẩn đoán về việc không có region để đóng hoặc region chưa được ghép cặp.

Sửa:

~~~java
// @start region=loadConfig
Properties properties = new Properties();
properties.load(input);
// @end region=loadConfig
~~~

Với region có tên, nên sao chép cùng một tên cho cả marker đầu và cuối thay vì gõ lại thủ công nhiều lần.

## 7. Lỗi thiếu @end: region đã mở nhưng chưa đóng

Ví dụ:

~~~java
// @start region=serverLifecycle
HttpServer server = HttpServer.create(address, 0);
server.createContext("/", handler);
server.start();
~~~

Region `serverLifecycle` đã được mở nhưng không có `@end`. Doclet có thể báo `unpaired region` và đánh dấu phần snippet có vấn đề.

Sửa:

~~~java
// @start region=serverLifecycle
HttpServer server = HttpServer.create(address, 0);
server.createContext("/", handler);
server.start();
// @end region=serverLifecycle
~~~

Một trường hợp ngược lại là có `@end` nhưng không có `@start`:

~~~java
server.start();
// @end region=serverLifecycle
~~~

Khi đó không có region tương ứng để đóng và có thể xuất hiện `no region to end`. Không nên thêm marker bắt đầu một cách máy móc; trước hết xác định xem `@end` thừa hay phần đầu của region bị thiếu.

## 8. Phân biệt region không tên và region có tên

Region không tên phù hợp với đoạn đơn giản, không lồng lấn:

~~~java
{@snippet :
    void run() { // @start
        initialize();
        execute();
    }             // @end
}
~~~

Với region lồng nhau, có thể dùng `@end` không tên vì mỗi lần đóng sẽ kết thúc region gần nhất chưa đóng:

~~~java
{@snippet :
    void run() {             // @start
        initialize();        // @start
        execute();           // @end
    }                        // @end
}
~~~

Nếu hai vùng chồng lấn hoặc không lồng nhau theo thứ tự đơn giản, hãy dùng tên:

~~~java
// @start region=setup
initialize();
// @start region=execution
execute();
// @end region=setup
cleanup();
// @end region=execution
~~~

Đặt tên giúp xác định rõ marker kết thúc thuộc vùng nào. Đừng dựa vào thứ tự của các `@end` không tên khi vùng chồng lấn.

## 9. Region do markup mở: tránh mở trùng

Hai dạng sau là hai cách khác nhau để bắt đầu một region.

Cách A — marker riêng:

~~~java
// @start region=important
server.start();
// @end region=important
~~~

Cách B — dùng markup có thuộc tính region:

~~~java
server.start(); // @highlight region=important substring="start()"
// @end region=important
~~~

Không ghép cả hai cách cho cùng một region:

~~~java
// @start region=important
server.start(); // @highlight region=important substring="start()"
// @end region=important
~~~

Ở ví dụ sai, `@start region=important` đã mở một vùng, sau đó `@highlight region=important` lại mở một vùng trùng tên. Điều này có thể tạo diagnostic region trùng hoặc cặp đầu/cuối không như mong muốn.

Nếu cần vừa chọn region vừa áp dụng highlight, chỉ cần dùng cách B. Nếu cần region chỉ để chọn phần hiển thị mà không cần highlight/replace/link, dùng cách A.

## 10. Markup cuối dòng tác động lên dòng nào?

Markup comment là comment cuối dòng trong ngôn ngữ được khai báo cho snippet. Nếu comment chứa markup hợp lệ, nó tác động lên dòng nguồn có comment đó.

Ví dụ highlight cùng dòng:

~~~java
{@snippet :
    server.start(); // @highlight substring="start()"
}
~~~

Markup comment không xuất hiện trong code hiển thị; chỉ phần `start()` được highlight.

Nếu comment markup kết thúc bằng dấu hai chấm `:`, markup được áp dụng như thể nó nằm ở cuối **dòng ngay sau**:

~~~java
{@snippet :
    // @highlight substring="start()" :
    server.start();
}
~~~

Cú pháp dấu hai chấm hữu ích khi:

- Comment markup dài và không muốn đặt sau dòng code.
- Định dạng của snippet không cho phép comment ở cuối dòng dữ liệu.
- Muốn áp dụng markup cho dòng tiếp theo mà không thay đổi nội dung của dòng đó.

Lưu ý: dấu hai chấm phải kết thúc comment markup. Nếu comment không kết thúc bằng `:`, Doclet áp dụng markup cho chính dòng comment, không phải dòng kế tiếp.

## 11. Giới hạn của markup cuối dòng trong Java text block

Trong Java source, không thể chèn comment `// ...` vào giữa nội dung của text block vì những ký tự đó là dữ liệu chuỗi, không phải comment Java.

Ví dụ không thể đặt markup comment ở giữa:

~~~java
String payload = """
    {
      "status": "OK" // @highlight substring="OK"
    }
    """;
~~~

Dòng `// @highlight` ở đây nằm trong nội dung text block, nên không được Java parser xem là comment markup. Nó trở thành văn bản của chuỗi và có thể làm thay đổi ví dụ.

### 11.1. Dùng region bao quanh text block

Đặt marker bên ngoài text block:

~~~java
{@snippet :
    // @highlight region=payload substring="OK"
    String payload = """
        {
          "status": "OK"
        }
        """;
    // @end region=payload
}
~~~

Markup bắt đầu trước câu lệnh và kết thúc sau dấu đóng text block. Doclet áp dụng highlight trong phạm vi region, còn nội dung chuỗi vẫn là Java source hợp lệ.

### 11.2. Dùng comment kết thúc bằng dấu hai chấm

Nếu chỉ cần áp dụng markup cho dòng tiếp theo, dùng cú pháp:

~~~java
{@snippet :
    // @highlight substring="String" :
    String payload = """
        {"status":"OK"}
        """;
}
~~~

Markup áp dụng cho dòng khai báo ngay sau comment. Cách này không đưa comment vào nội dung text block và không làm thay đổi chuỗi.

## 12. Giới hạn trong file properties

File properties sử dụng ký tự `#` hoặc `!` để mở comment dòng. Comment phải là ký tự đầu tiên không phải khoảng trắng trên dòng. Vì vậy, không thể đặt markup ở cuối một dòng thuộc tính như cách Java cho phép:

~~~properties
house.street=Main St. # @highlight substring="Main St."
~~~

Trong ví dụ trên, `# @highlight` có thể trở thành một phần của value, không phải comment markup.

Hãy đặt comment riêng và kết thúc bằng dấu hai chấm để áp dụng cho dòng kế tiếp:

~~~properties
# @start region=house
house.number=42
# @highlight substring="Main St." :
house.street=Main St.
house.town=AnyTown
# @end region=house
~~~

Markup comment được nhận diện nhờ `lang="properties"` hoặc phần mở rộng file properties. Trong JDK 18, Standard Doclet nhận diện `java` và `properties` là hai giá trị lang được hỗ trợ; hãy kiểm tra phiên bản JDK dùng để tạo tài liệu nếu chọn định dạng khác.

## 13. Một số lỗi markup khác dễ bị nhầm với lỗi region

Không phải mọi trường hợp markup không hiển thị đều là lỗi thiếu region:

| Hiện tượng | Nguyên nhân | Cách kiểm tra |
| --- | --- | --- |
| `@highligh` xuất hiện nguyên văn trong snippet | Tên markup bị gõ sai; tên không được nhận diện có thể bị bỏ qua và comment vẫn hiển thị. | Soát tên tag theo cú pháp `@highlight`, `@replace`, `@link`. |
| `@highlight` có tên đúng nhưng không tạo kết quả như mong muốn | Attribute sai, thiếu attribute bắt buộc hoặc giá trị không hợp lệ. | Đọc diagnostic của markup đã nhận diện; sửa attribute. |
| Snippet không tìm thấy file | Đường dẫn `file`/`class` sai hoặc file không nằm trong vùng tìm kiếm. | Kiểm tra `snippet-files` hoặc `--snippet-path`. |
| Region được tìm thấy nhưng nội dung hiển thị không đúng | Region bao gồm nhiều dòng hơn dự định hoặc marker đặt sai vị trí. | Kiểm tra vị trí bắt đầu/kết thúc và vùng lồng nhau. |
| Highlight không xuất hiện | `substring` hoặc `regex` không khớp nội dung trong phạm vi. | Kiểm tra chính xác text và regex; xem HTML được tạo. |
| Markup báo lỗi cú pháp | Tag được nhận diện nhưng có lỗi trong các attribute tiếp theo. | Sửa cú pháp; output của snippet trong trường hợp này không được bảo đảm. |

Một comment bắt đầu bằng `@` nhưng tên không được nhận diện có thể được bỏ qua như markup và xuất hiện trong output. Ngược lại, nếu tên tag hợp lệ nhưng các argument bị sai, Doclet báo lỗi; không nên dựa vào output tạo ra trong trường hợp đó.

## 14. Cách đọc diagnostic của Javadoc

Khi tạo tài liệu, Standard Doclet có thể báo lỗi và chèn diagnostic marker vào HTML tại vị trí mà nội dung không thể xử lý đúng. JDK 18 đã bổ sung hành vi này để người đọc tài liệu nhận biết output không đúng ý tác giả; công cụ cũng báo diagnostic và trả exit code phù hợp.

Quy trình kiểm tra:

1. Chạy `javadoc` bằng đúng JDK mà dự án sử dụng.
2. Đọc toàn bộ lỗi/warning liên quan đến `snippet`, `region` và tên file.
3. Tìm tên region trong tag `{@snippet}`.
4. Tìm cặp `@start`/`@end` hoặc markup có thuộc tính `region` trong file.
5. Sửa marker rồi chạy lại Javadoc.
6. Mở HTML được tạo, kiểm tra code hiển thị và diagnostic marker đã biến mất.

Ví dụ lệnh tạo Javadoc cho một package tree:

~~~bash
javadoc -d build/javadoc -sourcepath src/main/java -subpackages com.example
~~~

Có thể bật thêm DocLint để kiểm tra các vấn đề khác trong documentation comment:

~~~bash
javadoc -Xdoclint:all -d build/javadoc \
    -sourcepath src/main/java -subpackages com.example
~~~

DocLint hữu ích cho cú pháp, HTML và tham chiếu tài liệu, nhưng đừng dùng nó thay cho việc đọc diagnostic snippet/region của Standard Doclet. Kiểm tra cả exit code của lệnh và HTML được tạo.

## 15. Standard Doclet không biên dịch hoặc chạy snippet

Javadoc đọc và trình bày snippet; Standard Doclet không tự biên dịch hoặc thực thi đoạn code để chứng minh nó đúng. Một snippet có thể được hiển thị đẹp nhưng vẫn chứa code sai cú pháp hoặc không biên dịch.

Với external snippet, có thể dùng cùng file source làm đầu vào cho bước kiểm thử riêng:

~~~bash
javac -d build/snippet-classes src/main/java/com/example/snippets/ServerExamples.java
~~~

Nếu file chỉ là code fragment chứ không phải compilation unit hoàn chỉnh, cần đặt fragment vào một test/template thích hợp trước khi biên dịch. Với inline snippet, có thể dùng Compiler API/DocTrees hoặc trích đoạn theo quy trình kiểm thử của dự án.

Vì vậy, cần phân biệt:

- **Javadoc diagnostics:** kiểm tra cú pháp tag, region, đường dẫn file và markup.
- **javac/compiler diagnostics:** kiểm tra code có biên dịch được hay không.
- **Test runtime:** kiểm tra ví dụ có hoạt động đúng khi chạy hay không.

## 16. Giới hạn của inline snippet liên quan đến region

Inline snippet được viết ngay trong documentation comment nên có một số giới hạn do cú pháp comment bao quanh:

- Không thể chứa chuỗi ký tự `*/` vì nó kết thúc documentation comment.
- Dấu ngoặc nhọn `{` và `}` trong nội dung phải cân bằng và lồng nhau hợp lệ để Doclet xác định dấu đóng tag.
- Unicode escape sequence được xử lý trong giai đoạn phân tích source; không thể luôn phân biệt ký tự trực tiếp với dạng escape tương ứng.

Nếu ví dụ có block comment `/* ... */`, chuỗi chứa `*/` hoặc cấu trúc khó biểu diễn inline, hãy dùng external snippet. External snippet không có những giới hạn nội dung do nằm bên trong documentation comment.

Ví dụ external snippet:

~~~java
{@snippet file=ServerExamples.java region=serverStart}
~~~

File được đặt trong thư mục `snippet-files` cùng package hoặc trong đường dẫn khai báo với `--snippet-path`. Cách này cũng giúp dùng cùng source file cho tài liệu và kiểm thử.

## 17. Checklist sửa lỗi region

Khi Javadoc báo lỗi, rà theo thứ tự:

1. **Đúng file:** `file` hoặc `class` đang trỏ tới đúng external snippet.
2. **Đúng region được yêu cầu:** `region` trên `{@snippet}` trùng với tên marker.
3. **Có marker mở:** tồn tại `@start region=name` hoặc markup `@highlight/@replace/@link region=name`.
4. **Có marker đóng:** có `@end region=name` tương ứng.
5. **Tên chính xác:** không sai chữ hoa/thường, chính tả hoặc ký tự.
6. **Không đóng thừa:** mỗi `@end` có region đang mở để đóng.
7. **Không mở trùng:** không dùng đồng thời `@start region=name` và markup `region=name` cho cùng một vùng.
8. **Vùng lồng nhau đúng:** nếu dùng `@end` không tên, nó đóng region gần nhất chưa được đóng.
9. **Comment hợp lệ với ngôn ngữ:** Java text block và properties không cho phép mọi kiểu comment cuối dòng.
10. **Đọc HTML sau khi sửa:** xác nhận code được trích đúng và diagnostic marker đã biến mất.

## 18. Câu hỏi tự kiểm tra

1. Region được bắt đầu và kết thúc bằng những markup nào?
2. Khác biệt giữa `region` trên `{@snippet}` và `region` trên `@highlight` là gì?
3. `region not found` thường chỉ ra lỗi nào?
4. `unpaired region` khác `no region to end` như thế nào?
5. Vì sao tên region ở `@start` và `@end` phải khớp?
6. Khi nào dùng region không tên là phù hợp?
7. Vì sao các vùng chồng lấn nên dùng tên?
8. `@highlight region=name` có tự mở region không?
9. Markup comment mặc định áp dụng cho dòng nào?
10. Dấu hai chấm ở cuối markup comment thay đổi dòng áp dụng ra sao?
11. Vì sao không thể đặt `// @highlight` bên trong nội dung Java text block?
12. Làm thế nào áp dụng highlight cho một dòng trong text block?
13. Vì sao properties file không thể dùng comment markup ở cuối dòng thuộc tính?
14. Standard Doclet có tự biên dịch và chạy snippet không?
15. Khi nào nên chuyển inline snippet thành external snippet?

**Bài thực hành:** tạo một external snippet có region `serverStart` và tham chiếu từ `{@snippet file=... region=serverStart}`. Đổi tên region ở marker để tái hiện `region not found`; sửa lại cho khớp. Xóa `@end` để quan sát lỗi region chưa được ghép cặp, sau đó thêm lại. Cuối cùng đặt một text block trong snippet, thử áp dụng markup bằng comment cuối dòng bên trong chuỗi rồi chuyển marker ra ngoài text block bằng region hoặc cú pháp comment kết thúc bằng `:`.

## Tài liệu tham khảo chính thức

- [Oracle JDK 18 — Programmer's Guide to Snippets](https://docs.oracle.com/en/java/javase/18/code-snippet/index.html): cú pháp region, external snippets, giới hạn markup cuối dòng và cách kiểm thử snippet.
- [Oracle JDK 18 — Documentation Comment Specification](https://docs.oracle.com/en/java/javase/18/docs/specs/javadoc/doc-comment-spec.html): cú pháp `@snippet`, markup comment, region bắt đầu/kết thúc và hành vi khi markup sai.
- [Oracle JDK 18 — Release Notes](https://www.oracle.com/java/technologies/javase/18-relnote-issues.html): diagnostic marker và exit code khi Standard Doclet gặp nội dung không thể xử lý.
- [Oracle JDK 27 — Documentation Comment Specification](https://docs.oracle.com/en/java/javase/27/docs/specs/javadoc/doc-comment-spec.html): xác nhận cú pháp snippet, region và markup comment tiếp tục được hỗ trợ trên JDK hiện đại.
- [OpenJDK — Standard Doclet diagnostics](https://github.com/openjdk/jdk/blob/master/src/jdk.javadoc/share/classes/jdk/javadoc/internal/doclets/toolkit/resources/doclets.properties): các diagnostic về region không tìm thấy, không ghép cặp và không có region để đóng.
