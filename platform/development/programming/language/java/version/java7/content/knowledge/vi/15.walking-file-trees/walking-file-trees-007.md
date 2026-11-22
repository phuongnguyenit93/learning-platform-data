# Duyệt cây tệp trong Java: Xử lý tệp lỗi, bỏ qua nhánh hoặc kết thúc sớm

## 1. Bài toán và mục tiêu

Khi duyệt một thư mục có hàng nghìn tệp hoặc nhiều thư mục con, ứng dụng thường không muốn “đọc hết mọi thứ bằng mọi giá”. Những tình huống hay gặp:

- Một tệp không còn tồn tại đúng lúc tiến trình định đọc thuộc tính của nó.
- Một thư mục không thể mở vì quyền truy cập hoặc lỗi I/O.
- Một nhánh chứa cache, dữ liệu tạm hoặc thông tin ngoài phạm vi cần tìm nên phải **bỏ qua toàn bộ nhánh**.
- Khi gặp một tệp đủ điều kiện, chương trình chỉ muốn bỏ qua **những tệp cùng cấp còn lại**.
- Khi đã tìm thấy kết quả đầu tiên hoặc đạt giới hạn xử lý, cần **dừng toàn bộ việc duyệt**.
- Người vận hành cần biết một lượt quét đã **hoàn tất** hay **bị bỏ bớt/thất bại/dừng có chủ đích**.

Từ **Java 7**, Java NIO.2 cung cấp API:

```java
Files.walkFileTree(start, visitor);
```

trong đó `start` là một đối tượng `Path` và `visitor` triển khai `FileVisitor<Path>`. Với đa số nhu cầu, ta có thể kế thừa `SimpleFileVisitor<Path>` và override các callback cần thiết.

Điểm cốt lõi của bài học là phân biệt **ba nhóm quyết định**:

1. **Tiếp tục hoặc bỏ qua trong quá trình duyệt:** trả về `FileVisitResult.CONTINUE`, `SKIP_SUBTREE` hoặc `SKIP_SIBLINGS`.
2. **Kết thúc có chủ đích:** trả về `FileVisitResult.TERMINATE`.
3. **Báo thất bại thật sự:** ném hoặc truyền tiếp `IOException`, thay vì nuốt lỗi rồi âm thầm báo rằng việc quét đã thành công.

Các API trên **vẫn được hỗ trợ và sử dụng trong Java 17+ và Java hiện đại**. Ví dụ chạy đầy đủ của bài dùng JDK 17; không dựa vào kỹ thuật đã legacy.

## 2. Vòng đời callback của `FileVisitor`

`FileVisitor<T>` có bốn phương thức quan trọng khi `T` là `Path`:

| Callback | Khi nào được gọi | Giá trị hay thông tin quan trọng |
| --- | --- | --- |
| `preVisitDirectory(Path dir, BasicFileAttributes attrs)` | Trước khi duyệt nội dung một thư mục | Quyết định có đi vào nhánh hay không |
| `visitFile(Path file, BasicFileAttributes attrs)` | Khi thăm một mục được xử lý như file | Đọc metadata, ghi nhận tệp, tiếp tục/dừng/bỏ anh em |
| `visitFileFailed(Path file, IOException exc)` | Khi không thể thăm một mục vì lỗi I/O trong quy trình duyệt | Chính sách lỗi: bỏ qua có kiểm soát, bỏ các anh em, dừng hoặc ném lỗi |
| `postVisitDirectory(Path dir, IOException exc)` | Sau khi kết thúc việc duyệt thư mục, hoặc khi có lỗi khi duyệt các entry bên trong | `exc` có thể là `null` hoặc một `IOException` cần xử lý |

**Không nên hình dung một thư mục luôn có đủ cặp `preVisitDirectory`/`postVisitDirectory`.** Nếu `preVisitDirectory` trả `SKIP_SUBTREE` hoặc `SKIP_SIBLINGS` thì callback `postVisitDirectory` cho chính thư mục đó **không được gọi**. Nếu trả `TERMINATE`, việc duyệt kết thúc mà không có các callback hoàn tất tiếp theo. Nếu một callback ném exception, quá trình duyệt có thể bị hủy.

Hình dung một cây thư mục:

```text
root/
├── archive/
│   ├── old.log
│   └── images/
│       └── old.png
├── reports/
│   ├── 2025.csv
│   └── 2026.csv
└── config.json
```

Với chính sách “không đi vào `archive`”, khi `preVisitDirectory(archive, ...)` trả `SKIP_SUBTREE`, tệp `old.log`, thư mục `images` và `old.png` **không được thăm**. Các entry ngoài `archive` vẫn có thể được duyệt, trừ khi một lỗi hoặc quyết định khác dừng việc quét.

**Thứ tự liệt kê file trong cùng một thư mục không được dùng làm cam kết nghiệp vụ.** Không viết test giả định `2025.csv` luôn được thăm trước `2026.csv` chỉ vì tên đứng trước theo thứ tự chữ cái.

## 3. Bốn giá trị `FileVisitResult` và phạm vi ảnh hưởng

`FileVisitResult` là enum chứa bốn giá trị:

| Kết quả | Ý nghĩa trọng tâm | Dùng điển hình |
| --- | --- | --- |
| `CONTINUE` | Tiếp tục duyệt theo tiến trình bình thường | Xử lý xong một tệp, hoặc chấp nhận bỏ qua một lỗi cụ thể đã được ghi nhận |
| `SKIP_SUBTREE` | Không duyệt các mục bên dưới **thư mục hiện tại** | Trả từ `preVisitDirectory` khi cần bỏ qua một nhánh |
| `SKIP_SIBLINGS` | Bỏ qua **những entry anh em còn lại** trong thư mục cha tương ứng | Đã đạt mục tiêu ở một cấp, không cần xét các mục cùng cấp khác |
| `TERMINATE` | Chấm dứt toàn bộ việc duyệt | Đã tìm thấy kết quả đầu tiên, vượt quota hoặc nhận yêu cầu hủy có chủ đích |

Sự khác biệt quan trọng:

- **`SKIP_SUBTREE`** chủ yếu có ý nghĩa trong `preVisitDirectory`, khi đang quyết định có đi vào một thư mục hay không. Nó **không** có nghĩa “dừng chương trình” hoặc “bỏ mọi nhánh khác”.
- **`SKIP_SIBLINGS`** tác động đến các entry **cùng cấp còn lại**; nếu callback được gọi trong một thư mục con, các nhánh ngoài phạm vi cấp đó có thể vẫn được duyệt.
- **`TERMINATE`** dừng **toàn bộ** lời gọi `walkFileTree`. Trả về bình thường bằng giá trị này khác với ném một ngoại lệ I/O, và người gọi phải lưu trạng thái nếu cần phân biệt “hoàn tất” với “dừng sớm”.
- **`CONTINUE` sau lỗi** không làm lỗi biến mất về mặt nghiệp vụ: nếu việc thiếu một file ảnh hưởng tính đầy đủ, phải lưu số lượng lỗi, thông báo quét không đầy đủ hoặc chọn fail-fast.

### Lưu ý về callback đang chạy

Nếu chương trình ở trong `visitFile` thì callback nhận một file; trả `SKIP_SIBLINGS` không có nghĩa chỉ bỏ các file “cùng phần mở rộng”. Nếu muốn chọn theo loại, phải thiết kế điều kiện và tập cần xét trước đó.

Không trả `null` từ `FileVisitor`. API chờ một giá trị `FileVisitResult`; trả `null` có thể gây `NullPointerException` và không phải cách dừng duyệt.

## 4. Bắt đầu bằng `SimpleFileVisitor` và chiến lược mặc định

`SimpleFileVisitor<Path>` cung cấp implementation mặc định để ứng dụng chỉ override các callback liên quan:

```java
import java.io.IOException;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.attribute.BasicFileAttributes;

static void scan(Path start) throws IOException {
    Files.walkFileTree(start, new SimpleFileVisitor<Path>() {
        @Override
        public FileVisitResult visitFile(Path file,
                                         BasicFileAttributes attrs) {
            System.out.println(file.getFileName());
            return FileVisitResult.CONTINUE;
        }
    });
}
```

Đây là **phương thức hoàn chỉnh để đặt trong một lớp**, không yêu cầu thư viện bên ngoài. `SimpleFileVisitor` mặc định tiếp tục đối với các trường hợp thông thường và **không âm thầm nuốt lỗi I/O**: `visitFileFailed` mặc định truyền ngoại lệ; `postVisitDirectory` cũng truyền ngoại lệ nhận được khi `exc != null`.

**Vì sao đây là cơ sở tốt?** Nếu người viết chỉ cần đọc tên tệp, mặc định fail-fast trước lỗi I/O giúp tránh một kết quả “thành công” nhưng bỏ sót nhiều file vì permission hoặc lỗi đọc thư mục. Khi có nhu cầu bỏ lỗi có chọn lọc, override rõ những callback và trường hợp được phép.

## 5. Xử lý một tệp thất bại với `visitFileFailed`

Chữ ký:

```java
@Override
public FileVisitResult visitFileFailed(Path file, IOException exc)
        throws IOException {
    // Chọn chính sách.
}
```

`file` cho biết đường dẫn mà bộ duyệt đang cố thăm; `exc` là lỗi I/O liên quan. Lỗi có thể đến từ việc đọc thông tin entry, truy cập một thư mục hoặc các tình huống khác của traversal.

### 5.1. Bỏ qua có chọn lọc, không nuốt mọi lỗi

Giả sử ứng dụng lập danh sách các file **không bắt buộc**. Một file có thể biến mất vì tiến trình khác dọn dẹp đúng lúc quét. Nếu nghiệp vụ cho phép bỏ qua, ta có thể xử lý riêng `NoSuchFileException`:

```java
@Override
public FileVisitResult visitFileFailed(Path file, IOException exc)
        throws IOException {
    if (exc instanceof java.nio.file.NoSuchFileException) {
        System.err.println("Optional entry disappeared: "
                + file.getFileName());
        return FileVisitResult.CONTINUE;
    }
    throw exc;
}
```

Đoạn này là **phương thức override đặt trong `SimpleFileVisitor<Path>`**.

**Ý nghĩa chính xác:**

- Khi `NoSuchFileException` phù hợp với chính sách “entry tùy chọn có thể biến mất”, ta **ghi nhận** và trả `CONTINUE` để tiếp tục duyệt.
- Khi gặp `AccessDeniedException`, `FileSystemLoopException` hoặc `IOException` không được cho phép, ta **ném lại `exc`** để caller biết việc quét thất bại.
- Đối với một lần quét buộc phải đầy đủ, ngay cả `NoSuchFileException` cũng có thể phải được truyền tiếp.
- Không nhận diện loại lỗi bằng cách dò chuỗi `exc.getMessage().contains("not found")`; thông điệp không ổn định theo OS/provider/ngôn ngữ.

**Đừng nói chung chung rằng trả `CONTINUE` biến tệp lỗi thành tệp đã xử lý thành công.** Việc duyệt có thể tiến tiếp nhưng bản ghi lỗi vẫn chưa được đọc; cần phân biệt số file đã thăm và số file bị bỏ qua.

### 5.2. Bỏ qua các file anh em sau một lỗi

Nếu chính sách thực sự là “khi một entry ở thư mục hiện tại lỗi, dừng xử lý các entry khác của **chính thư mục đó**”, có thể trả:

```java
@Override
public FileVisitResult visitFileFailed(Path file, IOException exc) {
    recordFailure(file, exc); // Hàm ứng dụng tự định nghĩa.
    return FileVisitResult.SKIP_SIBLINGS;
}
```

Đây là đoạn **minh họa**, chưa độc lập vì `recordFailure` cần được tự định nghĩa. `SKIP_SIBLINGS` không chấm dứt toàn bộ traversal; vì vậy khi quét dữ liệu đòi đầy đủ, chính sách này cần đặc biệt thận trọng: nó có thể bỏ qua những file hoàn toàn hợp lệ cùng cấp.

### 5.3. Nếu gặp lỗi bắt buộc phải thất bại

Khi mất quyền đọc một directory quan trọng, giải pháp đơn giản thường là:

```java
@Override
public FileVisitResult visitFileFailed(Path file, IOException exc)
        throws IOException {
    throw exc;
}
```

Ném lỗi giúp caller nhận được `IOException`, ghi log đúng tầng và quyết định có retry, báo cáo hoặc hủy tác vụ. `TERMINATE` cũng dừng duyệt, nhưng **không tự mang ra ngoài một `IOException`**; nếu trả `TERMINATE` mà không lưu trạng thái lỗi, caller có thể hiểu nhầm là hoàn tất.

### 5.4. Không dựa vào việc cố tình thay quyền tệp khi viết test chạy mọi OS

Muốn kiểm thử `AccessDeniedException` bằng cách chỉnh ACL thư mục thường làm test phụ thuộc quyền tài khoản, hệ điều hành, filesystem và môi trường CI. Một test đơn vị có thể **gọi trực tiếp callback `visitFileFailed` với một `IOException` được tạo có chủ đích** để kiểm tra quyết định chính sách; nhưng phải nói rõ đó là **mô phỏng callback**, không phải bằng chứng bộ duyệt thật đã gặp lỗi permission.

Chương trình ở mục 14 kết hợp **duyệt tệp thật** cho các quyết định bỏ nhánh/dừng sớm và **gọi callback mô phỏng** để kiểm tra phân loại lỗi một cách ổn định.

## 6. `postVisitDirectory(dir, exc)`: lỗi khi duyệt nội dung thư mục

Callback này được gọi **sau khi kết thúc xử lý một thư mục**. Tham số `exc` có thể:

- Là `null` khi việc duyệt nội dung thư mục kết thúc bình thường.
- Là một `IOException` nếu xảy ra lỗi I/O trong quá trình liệt kê/duyệt các entry của thư mục.

Mẫu xử lý fail-fast rõ ràng:

```java
@Override
public FileVisitResult postVisitDirectory(Path dir, IOException exc)
        throws IOException {
    if (exc != null) {
        throw exc;
    }
    return FileVisitResult.CONTINUE;
}
```

Đây là **phương thức override** trong visitor.

### Phân biệt lỗi của một file và lỗi liệt kê directory

| Tình huống | Callback liên quan | Quyết định thường cần |
| --- | --- | --- |
| Không thể đọc metadata/mở entry để thăm | `visitFileFailed(file, exc)` | Tiếp tục có điều kiện hay truyền lỗi |
| Đang xử lý danh sách entry của directory thì có lỗi I/O | `postVisitDirectory(dir, exc)` | Thường báo lỗi nếu cần tính đầy đủ |
| Không muốn duyệt directory ngay từ đầu | `preVisitDirectory(dir, attrs)` | `SKIP_SUBTREE` |
| Tìm thấy kết quả mong muốn và không cần đi tiếp | `visitFile(file, attrs)` hoặc callback phù hợp | `TERMINATE` |
| Thân callback do ứng dụng viết tự ném `IOException` | Lỗi truyền ra từ `walkFileTree` | Caller catch; không tự động biến thành `visitFileFailed` |

**Điều dễ bị bỏ sót:** nếu override `postVisitDirectory` mà luôn trả `CONTINUE` bất chấp `exc != null`, ta có thể vô tình bỏ qua lỗi đọc thư mục và công bố kết quả không đầy đủ là đầy đủ.

### Nếu chủ đích chấp nhận thư mục lỗi thì sao?

Một bộ quét “best effort” có thể ghi nhận lỗi và trả `CONTINUE` để tiếp tục phần có thể truy cập. Nhưng khi đó cần:

1. Đánh dấu **quét không đầy đủ**.
2. Ghi lại file/path và loại lỗi trong báo cáo kỹ thuật phù hợp.
3. Không đưa thông báo “đã quét tất cả” nếu đã bỏ sót directory.
4. Để tầng nghiệp vụ quyết định có được phép sử dụng kết quả một phần hay không.

Một câu lệnh `CONTINUE` chỉ biểu diễn **đi tiếp trong traversal**, không phải một lời bảo đảm thành công.

## 7. `SKIP_SUBTREE`: bỏ qua nội dung một nhánh

Đây là kết quả thích hợp khi biết một directory không cần được xét, ví dụ thư mục cache hoặc thư mục được loại trừ theo cấu hình.

```java
@Override
public FileVisitResult preVisitDirectory(Path dir,
                                         BasicFileAttributes attrs) {
    if ("cache".equals(String.valueOf(dir.getFileName()))) {
        return FileVisitResult.SKIP_SUBTREE;
    }
    return FileVisitResult.CONTINUE;
}
```

Đây là **phương thức minh họa đặt trong visitor**. Việc kiểm tra tên `cache` chỉ hợp lý nếu quy tắc nghiệp vụ loại mọi thư mục mang tên đó. Khi cần loại đúng **một nhánh cụ thể**, hãy so sánh `Path` đã được xác định, chẳng hạn `dir.equals(ignoredPath)`, thay vì trùng tên tình cờ.

**Hành vi:**

- Không duyệt các file/thư mục con bên trong nhánh bị loại.
- Những nhánh khác có thể tiếp tục được duyệt.
- Không có lời gọi `postVisitDirectory` cho chính thư mục bị bỏ qua do `preVisitDirectory` trả `SKIP_SUBTREE`.
- Không tự xóa hoặc sửa nội dung thư mục; đây chỉ là điều khiển **traversal**, không phải thao tác `Files.delete`.

### Ví dụ mô hình

```text
root/
├── ignored/
│   └── secret.txt
├── kept/
│   └── visible.txt
└── root.txt
```

Nếu `preVisitDirectory(ignored)` trả `SKIP_SUBTREE`, visitor của phần tìm file sẽ chỉ ghi nhận `kept/visible.txt` và `root.txt`. Vì thứ tự liệt kê cùng cấp không bảo đảm, nên khi hiển thị kết quả trong unit test cần sắp xếp danh sách **sau traversal** trước khi so với danh sách dự kiến.

### Vì sao không dùng `return TERMINATE` ở đây?

`TERMINATE` sẽ **dừng toàn bộ việc duyệt**, làm mất cả `kept/visible.txt` và `root.txt` nếu các tệp đó chưa được xử lý. `SKIP_SUBTREE` giới hạn ảnh hưởng **chỉ một nhánh**, đúng với yêu cầu bỏ qua directory được loại.

## 8. `SKIP_SIBLINGS`: bỏ những entry cùng cấp còn lại

Giả sử ta duyệt một directory chỉ để lấy **một entry bất kỳ** đáp ứng điều kiện; khi đã gặp một file, có thể bỏ qua những file cùng cấp còn lại:

```java
@Override
public FileVisitResult visitFile(Path file, BasicFileAttributes attrs) {
    results.add(file); // Danh sách results do ứng dụng quản lý.
    return FileVisitResult.SKIP_SIBLINGS;
}
```

Đây là **đoạn minh họa có danh sách `results` được khai báo bên ngoài**. Khi thư mục hiện tại có ba file cùng cấp, kết quả là xử lý **một file** rồi bỏ qua những file còn lại. **Không dựa vào thứ tự tên tệp**: file đầu tiên có thể là `a.txt` hoặc tên khác tùy provider.

### `SKIP_SIBLINGS` khác `SKIP_SUBTREE`

- `SKIP_SUBTREE` trong `preVisitDirectory` không đi vào **nội dung của directory hiện tại** nhưng vẫn có thể thăm các entry cùng cấp của directory đó.
- `SKIP_SIBLINGS` từ `visitFile` dừng xử lý **những file/entry cùng cha** ở cấp hiện tại; không có nghĩa bỏ toàn bộ cây ngoài cấp đó.
- `SKIP_SIBLINGS` từ `preVisitDirectory` cũng có thể khiến directory hiện tại và các entry anh em còn lại không được duyệt; nó không giống “chỉ bỏ nội dung directory hiện tại”.

Một chiến lược “lấy một file trong **mỗi** thư mục” có thể dùng `SKIP_SIBLINGS` ở đúng cấp, nhưng cần cân nhắc xử lý thư mục con và tính đầy đủ. Nếu yêu cầu là “tìm kết quả đầu tiên của **cả cây**”, `TERMINATE` thường diễn đạt rõ hơn.

### Ảnh hưởng tới callback hậu duyệt

Khi `visitFile` trả `SKIP_SIBLINGS`, việc duyệt các sibling file còn lại bị bỏ. Nhưng thư mục cha vẫn có thể được **kết thúc bình thường** và callback `postVisitDirectory` của cha vẫn được gọi. Trong ví dụ kiểm thử của bài, ba file cùng một directory tạo kết quả **`visitFile` đúng một lần, `postVisitDirectory` cho directory đó đúng một lần**.

## 9. `TERMINATE`: kết thúc sớm toàn bộ quá trình duyệt

Nếu chương trình đang tìm một file theo điều kiện và **chỉ cần kết quả đầu tiên**, có thể dừng toàn bộ traversal:

```java
@Override
public FileVisitResult visitFile(Path file, BasicFileAttributes attrs) {
    if (file.getFileName() != null
            && file.getFileName().toString().endsWith(".json")) {
        found.set(file); // Một holder do ứng dụng định nghĩa.
        return FileVisitResult.TERMINATE;
    }
    return FileVisitResult.CONTINUE;
}
```

Đây là **đoạn minh họa**, chưa độc lập vì `found` cần được triển khai và gắn với loại phù hợp. Khi sử dụng thật, tránh lưu kết quả vào biến không an toàn nếu caller chạy đồng thời nhiều lượt quét.

**Hai điều phải hiểu:**

1. `TERMINATE` khiến `Files.walkFileTree` **kết thúc bình thường** sau quyết định dừng. Nó không mặc định ném ngoại lệ hay trả một enum trạng thái cho caller. Vì vậy cần một biến/hệ thống kết quả riêng để biết đã tìm thấy file hay hủy do giới hạn.
2. Không mong callback `postVisitDirectory` được gọi để “dọn dẹp nghiệp vụ” khi traversal bị terminate. Đừng chỉ đặt hành động bắt buộc trong `postVisitDirectory`.

### Dừng sớm có nghĩa quét không đầy đủ

Khi dùng `TERMINATE` để tìm **một** file, điều đó là **thành công có chủ đích** nếu hợp đồng chỉ cần một file. Nhưng khi dùng `TERMINATE` do một lỗi nghiêm trọng, kết quả là **thất bại có chủ đích**, không được hiển thị cùng trạng thái “tìm đủ tất cả tệp”.

Nếu ứng dụng có báo cáo thống kê, nên lưu:

```text
status = COMPLETED | STOPPED_EARLY | FAILED
visitedFiles = ...
skippedSubtrees = ...
visitFailures = ...
stopReason = ...
```

Đây là **mẫu trạng thái nghiệp vụ minh họa**, không phải kiểu Java dựng sẵn. `Files.walkFileTree` không tự tính và trả những con số này.

### `TERMINATE` không phải cơ chế hủy bất đồng bộ

Một giá trị `TERMINATE` chỉ được trả **từ một callback** đang chạy. Nếu thread đang mắc kẹt trong lời gọi I/O tại provider, chương trình không thể kỳ vọng việc đặt một biến boolean ở thread khác sẽ ngay lập tức gọi callback. Cơ chế cancellation, interrupt, timeout và đóng resource cần được thiết kế riêng cho môi trường thực tế.

## 10. Ném `IOException` từ callback: khác với `visitFileFailed`

Một nhầm lẫn thường gặp: “Nếu `visitFile` do mình viết ném `IOException`, `walkFileTree` sẽ gọi `visitFileFailed` để hỏi có tiếp tục không.”

**Không nên dựa vào giả định đó.** Lỗi từ **mã callback ứng dụng** được truyền ra khỏi `walkFileTree`; `visitFileFailed` chủ yếu phục vụ **lỗi của traversal khi cố thăm mục file system**.

Ví dụ cố ý dừng bằng lỗi:

```java
Files.walkFileTree(start, new SimpleFileVisitor<Path>() {
    @Override
    public FileVisitResult visitFile(Path file, BasicFileAttributes attrs)
            throws IOException {
        throw new IOException("visitor callback stopped");
    }
});
```

Đây là đoạn minh họa trong phương thức khai báo `throws IOException`. Ở tầng caller, `IOException` sẽ được truyền lên; không cần `visitFileFailed` tự động nuốt lỗi.

### Chọn giữa `TERMINATE` và `throw`

| Mục tiêu | Lựa chọn thường đúng | Vì sao |
| --- | --- | --- |
| Đã tìm thấy đủ một kết quả | `TERMINATE` | Dừng có chủ đích, không phải lỗi I/O |
| Đã đạt giới hạn số lượng kết quả theo cấu hình | `TERMINATE` cùng trạng thái | Dừng hợp lệ theo chính sách |
| Một file tùy chọn biến mất, quét vẫn được phép thiếu file đó | `visitFileFailed` + `CONTINUE` và ghi nhận | Không dừng cả cây vì một entry không bắt buộc |
| Không có quyền đọc directory bắt buộc | Ném tiếp `IOException`/`AccessDeniedException` | Caller biết không thể bảo đảm dữ liệu đầy đủ |
| Gặp lỗi khi xử lý nội dung tệp do ứng dụng tự thực hiện | Throw hoặc chuyển lỗi có cause phù hợp | Không biến lỗi dữ liệu thật thành “đã duyệt xong” |
| Người dùng hủy thao tác và ứng dụng chọn dừng ở callback kế tiếp | `TERMINATE` + trạng thái cancel | Phân biệt hủy với quét hoàn tất |

Một phương thức ở tầng cao có thể catch `IOException` để gắn ngữ cảnh nhiệm vụ, nhưng nên giữ **cause** và không phân loại mọi lỗi thành “file not found”.

## 11. Cây tệp có symbolic link và vòng liên kết

Theo mặc định, `Files.walkFileTree(start, visitor)` **không theo symbolic link** như khi yêu cầu `FOLLOW_LINKS`. Khi không theo liên kết, một symbolic link thường được thăm như một entry file theo metadata tương ứng.

Nếu muốn theo symbolic link:

```java
import java.nio.file.FileVisitOption;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.EnumSet;

// Đoạn minh họa trong phương thức có visitor được định nghĩa.
Files.walkFileTree(start,
        EnumSet.of(FileVisitOption.FOLLOW_LINKS),
        20,
        visitor);
```

Đây là minh họa dùng `maxDepth = 20`. Số `20` là lựa chọn **nghiệp vụ**, không phải giới hạn bắt buộc của Java. Việc đi theo symlink làm thay đổi phạm vi dữ liệu được duyệt và có thể tạo vòng liên kết.

Khi phát hiện vòng, traversal có thể đưa `FileSystemLoopException` vào `visitFileFailed`. Chúng ta cần một chính sách rõ:

- Nếu mục tiêu là inventory của **các entry đường dẫn bên trong một root**, thường nên bắt đầu bằng chế độ không theo links để tránh vô tình bước sang cây khác.
- Nếu mục tiêu thật sự yêu cầu theo links, phải quyết định cách xử lý vòng, độ sâu, quyền và tệp ngoài root.
- Không mặc định `SKIP_SUBTREE` sau khi đã đi vào một symlink sẽ luôn giữ được phạm vi bảo mật; nó chỉ điều khiển traversal theo những entry đã được nhận diện.
- Không coi việc bắt và bỏ qua toàn bộ `FileSystemLoopException` là an toàn cho mọi nghiệp vụ: dữ liệu quét có thể không đầy đủ.

### `maxDepth` không phải số file được duyệt

Overload:

```java
Files.walkFileTree(start, options, maxDepth, visitor);
```

giới hạn **độ sâu nhánh**, không giới hạn số lượng file. Khi đạt `maxDepth`, một directory ở mức độ sâu giới hạn có thể được xử lý như một file visit thay vì tiếp tục đi sâu; không suy ra rằng `preVisitDirectory` sẽ luôn chạy cho mọi directory nhìn thấy. Nếu muốn giới hạn **số file xử lý**, cần một bộ đếm nghiệp vụ và trả `TERMINATE` khi đủ điều kiện.

### Không theo symlink không thay thế kiểm soát quyền

Ngay cả trong chế độ không theo links, người dùng đối kháng có thể thay đổi file system giữa các thao tác. Khi quét một cây không tin cậy, cần chính sách xác minh root, quyền, symbolic link, giới hạn tài nguyên và mô hình đe dọa. Các phép `startsWith`/`normalize` trên `Path` chỉ là kiểm tra **giá trị đường dẫn**, không phải sandbox bảo mật toàn diện.

## 12. Duyệt theo “best effort” hay “fail fast”?

Hai chiến lược đều có chỗ dùng nhưng không nên trộn một cách mơ hồ.

### 12.1. Fail fast: ưu tiên kết quả đầy đủ hoặc báo thất bại

Phù hợp cho quét phục vụ kiểm kê tài sản, sao lưu bắt buộc, đối soát dữ liệu hoặc xử lý tuân thủ, nơi bỏ sót một file có thể làm sai kết quả.

Phương án:

```java
@Override
public FileVisitResult visitFileFailed(Path file, IOException exc)
        throws IOException {
    throw exc;
}

@Override
public FileVisitResult postVisitDirectory(Path dir, IOException exc)
        throws IOException {
    if (exc != null) throw exc;
    return FileVisitResult.CONTINUE;
}
```

Hai phương thức thuộc `FileVisitor<Path>`. Việc ném giúp caller nhận biết lỗi thật, thay vì xem một lượt quét thiếu dữ liệu là bình thường.

### 12.2. Best effort: chấp nhận một phần nhưng báo rõ

Phù hợp cho chỉ mục tìm kiếm có thể xây dựng lại, gợi ý UI hoặc quét phục vụ chẩn đoán không đòi bao phủ tuyệt đối.

Có thể làm:

```java
@Override
public FileVisitResult visitFileFailed(Path file, IOException exc) {
    failures.add(file); // Danh sách failures của ứng dụng.
    return FileVisitResult.CONTINUE;
}
```

Đây là **đoạn minh họa cần có danh sách `failures` bên ngoài**. Kết thúc traversal, kết quả nên mang:

- Danh sách kết quả đã đọc được.
- Số entry thất bại, loại lỗi và thông tin an toàn cho log.
- Trạng thái `PARTIAL` nếu số lỗi lớn hơn 0.
- Chính sách retry hoặc thông báo người dùng tùy độ quan trọng.

**Không báo `COMPLETED` với nghĩa “đã bao phủ mọi file” nếu lỗi thực tế bị bỏ qua.** Mọi ngoại lệ có thể chứa thông tin đường dẫn nhạy cảm; khi log hoặc hiển thị cần xử lý theo quyền, không đưa absolute path của server cho tất cả người dùng.

### 12.3. Chính sách tùy lỗi và tùy nhánh

Một phương án hiện đại là định nghĩa các nhóm:

| Nhóm | Ví dụ | Chính sách có thể chọn |
| --- | --- | --- |
| Tệp tùy chọn bị biến mất | `NoSuchFileException` dưới nhánh cache | Ghi nhận và `CONTINUE` |
| File bắt buộc không đọc được | `AccessDeniedException` trong dữ liệu chính | Throw, thất bại |
| Nhánh có chủ đích loại trừ | `preVisitDirectory` khớp `ignored` | `SKIP_SUBTREE`, không tính là lỗi |
| Không cần các file cùng cấp còn lại | Đã lấy một đại diện trong directory | `SKIP_SIBLINGS` |
| Đủ kết quả của toàn bộ tác vụ | Đã tìm một file hợp lệ | `TERMINATE`, trạng thái dừng có chủ đích |
| Directory bị lỗi khi liệt kê | `postVisitDirectory(exc != null)` | Thường throw, hoặc partial có ghi nhận |
| Symlink loop trong chế độ FOLLOW_LINKS | `FileSystemLoopException` | Theo chính sách vòng và phạm vi; không nuốt vô thức |

**Tránh gắn policy với tên exception một cách máy móc.** `NoSuchFileException` của tệp bắt buộc là một lỗi nghiêm trọng; `AccessDeniedException` của nhánh tùy chọn có thể cho phép bỏ qua trong một bài toán không cần đầy đủ. Hợp đồng nghiệp vụ quyết định.

## 13. Điều kiện kết thúc sớm không có nghĩa kết quả đầy đủ

Giả sử phần mềm quét một cây để tìm **bản sao cấu hình đầu tiên**. Khi gặp tệp hợp lệ và trả `TERMINATE`, lời gọi `walkFileTree` kết thúc mà **không ném lỗi**; tuy nhiên chưa thăm toàn bộ cây.

Cần phân biệt hai loại “thành công”:

1. **Tìm thấy một kết quả đủ dùng**, không cần duyệt tiếp: trạng thái `FOUND`, số file còn lại không quan trọng.
2. **Thu thập tất cả kết quả** theo hợp đồng: chỉ thành công đầy đủ khi mọi nhánh cần thiết đã được duyệt và không còn lỗi không được phép.

Mẫu trạng thái Java:

```java
enum ScanStatus {
    COMPLETED,
    STOPPED_EARLY,
    PARTIAL,
    FAILED
}
```

Đây là **enum minh họa để đặt trong lớp hoặc tệp riêng**. Tùy nghiệp vụ có thể thay bằng kiểu kết quả mang số file được thăm, số file lỗi, các nhánh đã bỏ qua có chủ đích và lý do dừng.

### Vì sao không chỉ dựa vào giá trị trả về của `walkFileTree`?

`Files.walkFileTree` trả một `Path` biểu diễn đường dẫn bắt đầu theo hợp đồng, **không trả** `FileVisitResult` cuối cùng hoặc danh sách file. Nếu một callback trả `TERMINATE`, caller vẫn có thể nhận kết quả trả bình thường. Hãy lưu **trạng thái dừng** trong visitor hoặc một cấu trúc kết quả do ứng dụng quản lý.

### Callback kết thúc thư mục không phải `finally`

Nếu bạn cần giải phóng tài nguyên ứng dụng **trong mọi trường hợp**, không đặt tất cả hành động đó chỉ trong `postVisitDirectory`; vì callback này có thể không được gọi khi skip/terminate/throw. Dùng `try/finally` hoặc `try-with-resources` tại đúng phạm vi sở hữu tài nguyên.

## 14. Ví dụ Java 17+ hoàn chỉnh: kiểm soát ba kiểu dừng và chính sách lỗi

Ví dụ dưới đây tạo cấu trúc tệp tạm, kiểm tra các ý nghĩa khác nhau một cách **không phụ thuộc thứ tự liệt kê file**:

- `SKIP_SUBTREE` loại `ignored` và `siblings` khỏi một lượt inventory, nhưng vẫn giữ các file cần xem.
- `SKIP_SIBLINGS` làm một lượt riêng trên directory ba file: xử lý đúng một file bất kỳ rồi bỏ hai file cùng cấp còn lại.
- `TERMINATE` dừng một lượt riêng khi thăm file đầu tiên, không gọi `postVisitDirectory` cho thư mục đang duyệt.
- Kiểm thử trực tiếp `visitFileFailed` với lỗi được tạo có chủ đích: cho qua `NoSuchFileException`, nhưng truyền `AccessDeniedException`.
- Kiểm thử trực tiếp `postVisitDirectory` khi nhận một `IOException` giả lập để xác nhận không nuốt lỗi directory.
- Kiểm chứng `IOException` do `visitFile` tự ném sẽ truyền ra khỏi `walkFileTree`.
- Dọn tệp và thư mục tạm ở cuối.

**Phân biệt rõ:** ba nhóm `SKIP_*` và `TERMINATE` chạy trên cây tệp thật; các dòng có tiền tố `simulated` là **unit test gọi callback trực tiếp**, không phải lỗi quyền hoặc directory iterator thực trên hệ thống tệp.

Tạo tệp **`WalkFailurePolicyDemo.java`**:

```java
import java.io.IOException;
import java.nio.file.AccessDeniedException;
import java.nio.file.FileVisitResult;
import java.nio.file.FileVisitor;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public final class WalkFailurePolicyDemo {
    private static void check(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }

    private static String display(Path path) {
        return path.toString().replace('\\', '/');
    }

    private static void deleteFixture(Path root) throws IOException {
        Files.walkFileTree(root, new SimpleFileVisitor<Path>() {
            @Override
            public FileVisitResult visitFile(Path file, BasicFileAttributes attrs)
                    throws IOException {
                Files.delete(file);
                return FileVisitResult.CONTINUE;
            }

            @Override
            public FileVisitResult postVisitDirectory(Path dir, IOException exc)
                    throws IOException {
                if (exc != null) throw exc;
                Files.delete(dir);
                return FileVisitResult.CONTINUE;
            }
        });
    }

    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("walk-policy-demo-");
        try {
            Path ignored = Files.createDirectory(root.resolve("ignored"));
            Files.writeString(ignored.resolve("secret.txt"), "secret");
            Path kept = Files.createDirectory(root.resolve("kept"));
            Files.writeString(kept.resolve("visible.txt"), "visible");
            Files.writeString(root.resolve("root.txt"), "root");
            Path siblings = Files.createDirectory(root.resolve("siblings"));
            Files.writeString(siblings.resolve("a.txt"), "a");
            Files.writeString(siblings.resolve("b.txt"), "b");
            Files.writeString(siblings.resolve("c.txt"), "c");

            List<String> visited = new ArrayList<>();
            int[] skippedDir = {0};
            Files.walkFileTree(root, new SimpleFileVisitor<Path>() {
                @Override
                public FileVisitResult preVisitDirectory(Path dir,
                                                         BasicFileAttributes attrs) {
                    if (dir.equals(ignored)) {
                        skippedDir[0]++;
                        return FileVisitResult.SKIP_SUBTREE;
                    }
                    if (dir.equals(siblings)) {
                        return FileVisitResult.SKIP_SUBTREE;
                    }
                    return FileVisitResult.CONTINUE;
                }

                @Override
                public FileVisitResult visitFile(Path file,
                                                 BasicFileAttributes attrs) {
                    visited.add(display(root.relativize(file)));
                    return FileVisitResult.CONTINUE;
                }

                @Override
                public FileVisitResult visitFileFailed(Path file, IOException exc)
                        throws IOException {
                    throw exc;
                }

                @Override
                public FileVisitResult postVisitDirectory(Path dir, IOException exc)
                        throws IOException {
                    if (exc != null) throw exc;
                    return FileVisitResult.CONTINUE;
                }
            });
            Collections.sort(visited);
            check(visited.equals(List.of("kept/visible.txt", "root.txt")),
                    "SKIP_SUBTREE must hide ignored and siblings");
            check(skippedDir[0] == 1, "ignored subtree intercepted");
            System.out.println("skip subtree files = " + visited);
            System.out.println("skip subtree count = " + skippedDir[0]);

            int[] siblingFiles = {0};
            int[] siblingPost = {0};
            Files.walkFileTree(siblings, new SimpleFileVisitor<Path>() {
                @Override
                public FileVisitResult visitFile(Path file,
                                                 BasicFileAttributes attrs) {
                    siblingFiles[0]++;
                    return FileVisitResult.SKIP_SIBLINGS;
                }

                @Override
                public FileVisitResult postVisitDirectory(Path dir, IOException exc)
                        throws IOException {
                    if (exc != null) throw exc;
                    siblingPost[0]++;
                    return FileVisitResult.CONTINUE;
                }
            });
            check(siblingFiles[0] == 1, "skip remaining sibling files");
            System.out.println("skip siblings visited = " + siblingFiles[0]);
            System.out.println("skip siblings post = " + siblingPost[0]);

            int[] terminatedFiles = {0};
            int[] terminatedPost = {0};
            Files.walkFileTree(siblings, new SimpleFileVisitor<Path>() {
                @Override
                public FileVisitResult visitFile(Path file,
                                                 BasicFileAttributes attrs) {
                    terminatedFiles[0]++;
                    return FileVisitResult.TERMINATE;
                }

                @Override
                public FileVisitResult postVisitDirectory(Path dir, IOException exc)
                        throws IOException {
                    terminatedPost[0]++;
                    return FileVisitResult.CONTINUE;
                }
            });
            check(terminatedFiles[0] == 1 && terminatedPost[0] == 0,
                    "TERMINATE stops without post callbacks");
            System.out.println("terminate files = " + terminatedFiles[0]);
            System.out.println("terminate post = " + terminatedPost[0]);

            int[] allowedMissing = {0};
            FileVisitor<Path> policy = new SimpleFileVisitor<Path>() {
                @Override
                public FileVisitResult visitFileFailed(Path file, IOException exc)
                        throws IOException {
                    if (exc instanceof NoSuchFileException) {
                        allowedMissing[0]++;
                        return FileVisitResult.CONTINUE;
                    }
                    throw exc;
                }

                @Override
                public FileVisitResult postVisitDirectory(Path dir, IOException exc)
                        throws IOException {
                    if (exc != null) throw exc;
                    return FileVisitResult.CONTINUE;
                }
            };
            FileVisitResult decision = policy.visitFileFailed(
                    root.resolve("missing.txt"),
                    new NoSuchFileException("missing.txt"));
            check(decision == FileVisitResult.CONTINUE && allowedMissing[0] == 1,
                    "controlled missing-file callback policy");
            System.out.println("simulated missing = " + decision);

            boolean deniedPropagated = false;
            try {
                policy.visitFileFailed(root.resolve("blocked.txt"),
                        new AccessDeniedException("blocked.txt"));
            } catch (AccessDeniedException expected) {
                deniedPropagated = true;
            }
            check(deniedPropagated, "access denied must not be swallowed");
            System.out.println("simulated denied propagated = " + deniedPropagated);

            boolean directoryFailurePropagated = false;
            try {
                policy.postVisitDirectory(root,
                        new IOException("synthetic directory failure"));
            } catch (IOException expected) {
                directoryFailurePropagated = true;
            }
            check(directoryFailurePropagated,
                    "post-visit directory error propagates");
            System.out.println("simulated directory failure propagated = "
                    + directoryFailurePropagated);

            boolean callbackExceptionPropagated = false;
            try {
                Files.walkFileTree(siblings, new SimpleFileVisitor<Path>() {
                    @Override
                    public FileVisitResult visitFile(Path file,
                                                     BasicFileAttributes attrs)
                            throws IOException {
                        throw new IOException("visitor callback stopped");
                    }
                });
            } catch (IOException expected) {
                callbackExceptionPropagated =
                        "visitor callback stopped".equals(expected.getMessage());
            }
            check(callbackExceptionPropagated,
                    "IOException thrown by callback aborts walk");
            System.out.println("callback IOException propagated = "
                    + callbackExceptionPropagated);
        } finally {
            deleteFixture(root);
        }
        System.out.println("cleanup = done");
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac --release 17 -Xlint:all -Werror -encoding UTF-8 WalkFailurePolicyDemo.java
java WalkFailurePolicyDemo
```

**Stdout chính xác đã kiểm thử với hệ thống tệp mặc định trên Windows:**

```text
skip subtree files = [kept/visible.txt, root.txt]
skip subtree count = 1
skip siblings visited = 1
skip siblings post = 1
terminate files = 1
terminate post = 0
simulated missing = CONTINUE
simulated denied propagated = true
simulated directory failure propagated = true
callback IOException propagated = true
cleanup = done
```

### 14.1. Vì sao kết quả của `SKIP_SUBTREE` ổn định?

Visitor chỉ ghi nhận file dưới `kept` và file `root.txt`; nhánh `ignored` bị loại theo đúng `Path` và nhánh `siblings` bị loại trong lượt inventory này. Danh sách sau đó được **`Collections.sort`** để không dựa vào thứ tự traversal mà hệ điều hành cung cấp. Các tên được biểu diễn với `/` để hiển thị thống nhất Windows/Unix, nhưng tất cả thao tác đường dẫn thật đều dùng `Path`.

### 14.2. Vì sao `SKIP_SIBLINGS` cho đúng một file?

Lượt thứ hai chỉ duyệt một thư mục `siblings` chứa ba file. `visitFile` của file đầu tiên trả `SKIP_SIBLINGS`, khiến hai entry còn lại không được thăm. Code **không in tên file đầu tiên** vì thứ tự file không được bảo đảm. `postVisitDirectory` vẫn được gọi cho directory đang duyệt và đếm `1` trong tình huống này.

### 14.3. Vì sao `TERMINATE` khác `SKIP_SIBLINGS`?

Lượt thứ ba gặp một file thì trả `TERMINATE`. Vì toàn bộ traversal ngừng ngay, callback `postVisitDirectory` không chạy, nên bộ đếm hậu duyệt là `0`. Đây là khác biệt quan trọng nếu code định cập nhật một bộ đếm hoặc giải phóng tài nguyên trong `postVisitDirectory`.

### 14.4. Phần kiểm thử callback mô phỏng

Các dòng `simulated missing`, `simulated denied propagated` và `simulated directory failure propagated` được tạo bằng cách **trực tiếp gọi các phương thức của visitor với exception được dựng trong test**. Lý do: test này không cần thay quyền thư mục, xóa tệp giữa các luồng hoặc tạo một lỗi I/O không ổn định để ép callback.

Nó kiểm chứng **đúng nhánh điều kiện và hành vi trả/throw của callback**; nó không chứng minh mọi provider sẽ phát sinh đúng ngoại lệ đó trong cùng hoàn cảnh. Phần giao tiếp thật với filesystem cần integration test theo môi trường khi ứng dụng có yêu cầu cụ thể.

### 14.5. Bước cuối: lỗi do callback tự ném

Lượt cuối trực tiếp ném `IOException("visitor callback stopped")` từ `visitFile`. `walkFileTree` truyền lỗi lên caller, sau đó mã kiểm tra thông điệp do **chính chương trình tạo** để xác nhận luồng. Trong production, logic không nên phân loại **lỗi hệ điều hành** bằng chuỗi message; ở đây message tự tạo chỉ dùng xác minh một điều kiện test nội bộ.

### 14.6. Cleanup không phụ thuộc việc traversal thử nghiệm hoàn tất

Khối `finally` gọi `deleteFixture(root)` để dọn sạch cây thử nghiệm. Đây là **cây tệp do chính test tạo trong thư mục tạm**, không phải lời khuyên xóa đệ quy một thư mục tùy ý của người dùng. Phương thức dọn xóa file ở `visitFile` rồi xóa directory ở `postVisitDirectory`, ném lại lỗi directory nếu có.

Nếu môi trường từ chối tạo/xóa thư mục tạm hoặc có tác nhân bên ngoài thay đổi cây, chương trình vẫn có thể gặp `IOException`. Các kết quả stdout trên được kiểm chứng trong môi trường kiểm thử đã nêu, không phải lời cam kết cho mọi file-system provider.

## 15. Thiết kế test để không phụ thuộc thứ tự và quyền của hệ điều hành

Một bộ test về điều khiển traversal nên tập trung vào **bất biến**:

| Chính sách | Fixture / input | Điều cần xác minh |
| --- | --- | --- |
| `CONTINUE` bình thường | Một cây nhỏ | Những entry nằm trong phạm vi đều được xử lý |
| `SKIP_SUBTREE` | Một nhánh bị loại và một nhánh giữ lại | Không có file nào trong nhánh bị loại xuất hiện; nhánh khác vẫn có kết quả |
| `SKIP_SIBLINGS` | Directory có nhiều file cùng cấp | Chỉ một file được thăm sau điều kiện dừng sibling, không buộc tên file nào |
| `TERMINATE` | Có ít nhất một file | Trả về sau một file; không gọi hậu duyệt ở nhánh đang dừng |
| `visitFileFailed` bỏ qua lỗi cho phép | Gọi trực tiếp với `NoSuchFileException` mô phỏng | `CONTINUE` và bộ đếm lỗi tăng |
| `visitFileFailed` trên lỗi không được phép | Gọi trực tiếp với `AccessDeniedException` | Exception được truyền tiếp |
| `postVisitDirectory` có `exc != null` | Gọi trực tiếp với `IOException` mô phỏng | Không nuốt lỗi directory |
| Callback tự ném exception | `visitFile` ném `IOException` | Caller nhận lỗi; traversal ngừng |
| FOLLOW_LINKS | Fixture symlink kiểm soát được | Không treo; áp dụng chính sách loop/rủi ro |
| Max depth | Cây có nhiều cấp | Không xử lý dữ liệu sâu quá ngưỡng mong muốn |

**Không nên tạo test ép lỗi permission bằng cách xóa ACL hệ thống hoặc thay quyền những thư mục thật.** Dùng test mô phỏng cho chính sách callback; dành integration test filesystem cho môi trường được cấu hình và cho phép.

### Test “thất bại một phần” cần kiểm tra chất lượng kết quả

Giả sử visitor bỏ qua lỗi file để thu thập danh sách file có thể truy cập. Khi kết thúc, test không nên chỉ kiểm tra danh sách có vài phần tử. Nó phải xác nhận:

- Có bao nhiêu file được thăm.
- Có bao nhiêu lỗi bị cho phép bỏ qua.
- Những lỗi không được phép đã được truyền ra.
- Có bao nhiêu nhánh bị bỏ qua có chủ đích.
- Trạng thái cuối phản ánh **partial/complete/stopped** đúng hợp đồng.

Nếu một công cụ backup chỉ trả `CONTINUE` cho mọi lỗi rồi in “sao lưu thành công”, đó là **lỗi nghiệp vụ** ngay cả khi API Java được gọi đúng cú pháp.

## 16. Độ tin cậy, hiệu năng và an toàn dữ liệu

### 16.1. Giới hạn phạm vi và số entry

Một cây có thể rất sâu hoặc rất rộng, và directory entries có thể thay đổi khi đang duyệt. `maxDepth` giới hạn **độ sâu**, còn đếm số file và trả `TERMINATE` có thể giới hạn **số entry đã thăm**. Nếu cần timeout hoặc quota tài nguyên, thiết kế thêm hạn mức theo số file, byte đọc, thời gian và số lỗi cho phép.

Không suy ra rằng việc duyệt có thể hoàn thành ngay tức thì chỉ vì `FileVisitor` dùng callback. Nó vẫn cần filesystem I/O và có thể tốn thời gian với ổ đĩa mạng hoặc ổ đĩa chứa nhiều entry.

### 16.2. Duyệt và đọc nội dung là hai công việc khác nhau

`walkFileTree` đưa các entry và `BasicFileAttributes` đến visitor; nếu trong `visitFile` bạn còn đọc file bằng `Files.readAllBytes`, thao tác đó có thể phát sinh **một lỗi riêng ở mức nội dung** sau khi entry đã được thăm thành công.

Ví dụ:

```java
@Override
public FileVisitResult visitFile(Path file, BasicFileAttributes attrs)
        throws IOException {
    byte[] bytes = Files.readAllBytes(file);
    inspect(bytes); // Hàm xử lý nội dung do ứng dụng định nghĩa.
    return FileVisitResult.CONTINUE;
}
```

Đây là **đoạn minh họa**, không độc lập vì `inspect` cần được định nghĩa. Nếu `Files.readAllBytes` ném `IOException`, lỗi truyền ra khỏi callback; `visitFileFailed` không tự động xử lý lỗi logic của chính callback.

Nếu thực sự muốn bỏ qua lỗi đọc nội dung có chọn lọc, hãy bắt **ngay trong `visitFile`** và trả `CONTINUE` theo chính sách, đồng thời ghi nhận phần dữ liệu bị bỏ qua. Đối với file lớn, không dùng `readAllBytes` vô hạn; chọn stream/buffer và giới hạn số byte.

### 16.3. Tránh giả định tính nhất quán của snapshot

File có thể bị đổi tên, xóa, tạo mới hoặc sửa nội dung ngay trong lúc traversal. `BasicFileAttributes` được cung cấp cho một entry **không phải khóa file** và không bảo đảm trạng thái sẽ còn như vậy khi mở file sau đó.

Đối với bản sao lưu hoặc kiểm kê cần dữ liệu nhất quán, phải cân nhắc filesystem snapshot, cơ chế sở hữu/khóa ứng dụng hoặc quy trình kiểm chứng sau quét. Một lượt `walkFileTree` bình thường không tự tạo snapshot transaction.

### 16.4. Quyền truy cập và log an toàn

`IOException` và `FileSystemException` có thể chứa đường dẫn tuyệt đối hoặc chi tiết hệ thống. Đừng đưa trực tiếp stack trace, tên thư mục người dùng hoặc đường dẫn server trong response công khai. Log kỹ thuật có thể chứa loại lỗi, operation, đường dẫn đã được lọc và correlation ID, được bảo vệ theo chính sách truy cập.

Trả `SKIP_SUBTREE` hoặc `CONTINUE` sau lỗi permission **không làm tăng quyền truy cập**. Nó chỉ tránh duyệt những entry không thể hoặc không nên truy cập.

## 17. So sánh `walkFileTree` với `Files.walk` và `Files.find`

Java có những API duyệt cây khác:

| API | Kiểu giao diện | Kiểm soát lỗi và bỏ nhánh |
| --- | --- | --- |
| `Files.walkFileTree` (Java 7+) | Callback `FileVisitor` | Trực tiếp có `visitFileFailed`/`postVisitDirectory`, `SKIP_SUBTREE`/`SKIP_SIBLINGS`/`TERMINATE` |
| `Files.walk` (Java 8+) | `Stream<Path>` | Tiện pipeline, nhưng không trả `FileVisitResult` cho từng callback; có thể phát sinh `UncheckedIOException` khi duyệt |
| `Files.find` (Java 8+) | `Stream<Path>` với predicate nhận `BasicFileAttributes` | Phù hợp lọc trong pipeline; không thay thế các nhánh điều khiển tùy loại lỗi của visitor |

Nếu yêu cầu là “khi file lỗi thì chọn skip/dừng, bỏ nhánh ngay từ `preVisitDirectory`”, `walkFileTree` thường là lựa chọn rõ ràng hơn. Nếu chỉ cần pipeline lọc danh sách Path thông thường, `Files.walk` hoặc `Files.find` có thể gọn hơn.

**Khác biệt quản lý tài nguyên:** stream trả về từ `Files.walk`/`Files.find` cần được đóng, ví dụ bằng `try-with-resources`; bản thân `walkFileTree` thực hiện vòng đời traversal trong lời gọi phương thức và không trả một stream để caller đóng.

```java
try (java.util.stream.Stream<Path> paths = Files.walk(start)) {
    long count = paths.filter(Files::isRegularFile).count();
    System.out.println(count);
}
```

Đây là **đoạn minh họa** có biến `start` kiểu `Path` và xử lý `IOException`, cần kiểm soát kết quả theo filesystem thực tế. `Files.walk` không cho bạn quyền trả `SKIP_SUBTREE` từ lambda `filter`; việc filter kết quả **không đồng nghĩa** với ngăn quá trình đi sâu vào directory đó.

## 18. Những sai lầm phổ biến

| Sai lầm | Vì sao gây lỗi | Cách khắc phục |
| --- | --- | --- |
| Trả `CONTINUE` cho mọi `IOException` mà không ghi nhận | Kết quả quét thiếu dữ liệu nhưng bị báo đầy đủ | Chỉ bỏ qua lỗi được cho phép, lưu số lỗi và trạng thái PARTIAL |
| Nghĩ `SKIP_SUBTREE` dừng toàn bộ cây | Nhánh khác vẫn có thể được thăm | Dùng `TERMINATE` nếu muốn kết thúc toàn bộ |
| Nghĩ `SKIP_SIBLINGS` chỉ bỏ file cùng đuôi | Bỏ những entry anh em còn lại, không xét phần mở rộng | Xác định phạm vi sibling và điều kiện đúng |
| Dùng `TERMINATE` để báo lỗi mà không lưu trạng thái | Caller thấy `walkFileTree` trả bình thường | Rethrow `IOException` hoặc lưu trạng thái FAILED rõ ràng |
| Mong `postVisitDirectory` luôn chạy cho mọi directory | Bị skip/terminate/throw có thể không có callback | Dùng `finally` cho cleanup bắt buộc |
| Override `postVisitDirectory` rồi bỏ qua `exc` | Nuốt lỗi liệt kê directory | Nếu `exc != null`, throw hoặc ghi nhận partial có chủ đích |
| Nghĩ `visitFileFailed` bắt lỗi do mã `visitFile` tự ném | Exception callback có thể truyền lên caller ngay | Bắt trong callback nếu chính sách cho phép |
| Đoán thứ tự file theo tên | Directory iteration order không được bảo đảm | Sắp xếp kết quả sau duyệt khi cần |
| Đếm `SKIP_SIBLINGS` như quét đầy đủ | Những sibling còn lại chưa được xử lý | Ghi trạng thái bỏ qua có chủ đích |
| Theo symlink mà không xử lý vòng | Có thể gặp `FileSystemLoopException` hoặc vượt phạm vi | Chọn FOLLOW_LINKS có chủ đích, giới hạn độ sâu và policy vòng |
| Coi `maxDepth` là số lượng file tối đa | Chỉ giới hạn độ sâu | Tự đếm file và kết thúc theo quota |
| Xem `BasicFileAttributes` là trạng thái bất biến | File có thể thay đổi trong lúc duyệt | Xử lý I/O thật và lỗi/race |
| Dùng `readAllBytes` trên mọi file trong `visitFile` | Rủi ro bộ nhớ khi file lớn | Dùng stream/buffer/quota khi cần |
| In raw absolute paths trong log công khai | Có thể lộ thông tin hệ thống | Log có kiểm soát và thông báo an toàn |
| Chỉ bắt `NoSuchFileException` và coi mọi quyền truy cập đều ổn | Provider có thể phát sinh subclass khác | Có nhánh `IOException` dự phòng |
| Dùng `Files.walk` rồi tưởng `filter` ngăn đi xuống nhánh | Stream filter không có ý nghĩa skip subtree | Dùng `walkFileTree` với `preVisitDirectory` |
| Coi trả `null` là một giá trị visit hợp lệ | Có thể ném lỗi | Luôn trả enum `FileVisitResult` |
| Dùng directory thật của người dùng trong test xóa | Có nguy cơ mất dữ liệu | Dùng fixture tạo trong temp directory và dọn đúng phạm vi |
| Test quyền bằng cách sửa ACL toàn hệ thống | Test phụ thuộc OS/quyền, không an toàn | Test policy bằng callback mô phỏng, integration test tách biệt |

## 19. Bài tập và đáp án

### Bài 1 — Bỏ qua nhánh cache

Một chương trình quét `root`, khi tới thư mục `root/cache` thì không cần bất kỳ file nào bên dưới, nhưng vẫn muốn duyệt các nhánh còn lại. Trả kết quả gì, từ callback nào?

**Đáp án:** Tại `preVisitDirectory` khi `dir.equals(cachePath)`, trả `FileVisitResult.SKIP_SUBTREE`. Các nhánh khác vẫn được duyệt; `postVisitDirectory` không được gọi cho chính directory vừa bỏ.

### Bài 2 — Tìm một file đầu tiên trong toàn bộ cây

Ứng dụng chỉ cần tìm **một** file khớp điều kiện; không cần quét tiếp bất kỳ nhánh nào. Dùng `SKIP_SIBLINGS` hay `TERMINATE`?

**Đáp án:** `TERMINATE`, vì muốn dừng **toàn bộ** lượt duyệt. Lưu `Path` đã tìm thấy trong một cấu trúc kết quả riêng trước khi trả `TERMINATE`.

### Bài 3 — Chỉ lấy một entry trong mỗi directory

Nếu `visitFile` trả `SKIP_SIBLINGS` sau file đầu tiên, chương trình có đang đảm bảo đã đọc một **file có tên nhỏ nhất theo thứ tự chữ cái** không?

**Đáp án:** Không. Thứ tự duyệt các sibling entry không được bảo đảm. Muốn file có tên nhỏ nhất, phải thu thập và so sánh theo quy tắc của ứng dụng, hoặc chọn chiến lược sắp xếp phù hợp; `SKIP_SIBLINGS` chỉ bỏ qua những entry còn lại, không chọn theo tên.

### Bài 4 — Lỗi file tùy chọn

Một file có thể bị tiến trình khác xóa khi quét cây cache, và ứng dụng cho phép mất file đó. `visitFileFailed` nhận `NoSuchFileException` thì nên làm gì?

**Đáp án:** Nếu chính sách cho phép, ghi nhận file bị bỏ qua, tăng bộ đếm lỗi/thay đổi và trả `CONTINUE`. Các lỗi không được cho phép nên ném tiếp. Nếu quét yêu cầu đầy đủ tuyệt đối, kể cả lỗi thiếu file cũng phải làm lượt quét thất bại.

### Bài 5 — Thư mục lỗi trong `postVisitDirectory`

`postVisitDirectory(dir, exc)` nhận `exc != null`. Trả `CONTINUE` mà không ghi nhận gì có vấn đề gì?

**Đáp án:** Có thể che lỗi khi liệt kê directory và làm kết quả không đầy đủ bị báo là đầy đủ. Thông thường cần ném `exc`; nếu cho phép partial, phải ghi nhận lỗi và phản ánh trong trạng thái kết quả.

### Bài 6 — Lỗi do chính callback

Trong `visitFile`, ứng dụng gọi một API đọc nội dung và API đó ném `IOException`. Có thể tin rằng `walkFileTree` sẽ tự gọi `visitFileFailed` cho lỗi nội dung này không?

**Đáp án:** Không. Exception từ callback có thể truyền trực tiếp ra khỏi `walkFileTree`. Nếu muốn xử lý nội bộ, phải đặt `try/catch` trong `visitFile` theo chính sách, hoặc để caller catch khi thất bại.

### Bài 7 — Tại sao không dùng `postVisitDirectory` để đóng tài nguyên chính?

Ứng dụng trả `TERMINATE` từ `visitFile` nhưng lại chỉ đóng tệp output trong `postVisitDirectory`. Điều gì có thể xảy ra?

**Đáp án:** Callback hậu duyệt có thể không chạy sau `TERMINATE`, khiến tài nguyên không được đóng như mong đợi. Quản lý tài nguyên bằng `try-with-resources` hoặc `finally` trong phạm vi sở hữu tương ứng.

### Bài 8 — Hạn chế độ sâu

Muốn không đi sâu quá 5 cấp, nên dùng `maxDepth = 5` hay `SKIP_SIBLINGS`?

**Đáp án:** `maxDepth = 5` trong overload `Files.walkFileTree(start, options, maxDepth, visitor)` khi mong muốn chỉ giới hạn độ sâu. `SKIP_SIBLINGS` bỏ các entry cùng cấp, không tự biểu diễn giới hạn độ sâu.

### Bài 9 — Symlink loop

Một lượt duyệt bật `FOLLOW_LINKS` và gặp `FileSystemLoopException`. Nên xử lý thế nào?

**Đáp án:** Xem yêu cầu nghiệp vụ: nếu bắt buộc đầy đủ, báo lỗi; nếu cho phép bỏ qua vòng, ghi nhận thiếu nhánh và áp dụng chính sách tiếp tục phù hợp. Không tự động theo link trong mọi tình huống và không coi việc bỏ lỗi là quét đầy đủ.

### Bài 10 — Kết thúc sớm không có exception

Sau khi `visitFile` trả `TERMINATE`, `Files.walkFileTree` trả bình thường. Có thể suy ra đã quét toàn bộ cây không?

**Đáp án:** Không. `TERMINATE` là một quyết định dừng có chủ đích, không phải ngoại lệ. Caller phải đọc trạng thái do visitor/tầng ứng dụng quản lý để biết đã dừng sớm.

### Bài 11 — Kiểm thử không phụ thuộc OS

Vì sao bài thực hành gọi trực tiếp `policy.visitFileFailed(path, new AccessDeniedException(...))`, thay vì thay đổi quyền thư mục tạm để ép access denied?

**Đáp án:** Mục tiêu unit test là kiểm tra **nhánh chính sách của callback**, có thể được xác minh bằng exception mô phỏng không cần quyền đặc biệt. Lỗi permission thật phụ thuộc OS/provider/quyền CI và nên được test riêng trong môi trường có kiểm soát.

### Bài 12 — Khi nào `Files.walk` không thay thế được `walkFileTree`?

Một tác vụ cần bỏ cả thư mục khi `preVisitDirectory` phát hiện nằm trong danh sách loại trừ, đồng thời xử lý riêng lỗi từng entry. Chọn API nào?

**Đáp án:** `Files.walkFileTree` kết hợp `SimpleFileVisitor`, vì nó cho phép trả `SKIP_SUBTREE` trước khi vào nhánh và override `visitFileFailed`/`postVisitDirectory`. `Files.walk` trả stream để lọc kết quả nhưng `filter` không phải lệnh ngăn filesystem walker đi sâu vào nhánh.

## 20. Checklist thực hành

- [ ] Đã xác định mục tiêu quét là **đầy đủ**, **best effort**, **tìm một kết quả** hay **giới hạn số file**.
- [ ] Dùng đúng callback cho từng quyết định: `preVisitDirectory` để bỏ nhánh; `visitFileFailed` cho lỗi thăm entry; `postVisitDirectory` cho lỗi duyệt directory.
- [ ] Phân biệt phạm vi `SKIP_SUBTREE`, `SKIP_SIBLINGS` và `TERMINATE`.
- [ ] Không mặc định `postVisitDirectory` sẽ chạy sau skip/terminate/throw.
- [ ] Không trả `CONTINUE` khi lỗi nghiêm trọng chưa được ghi nhận hoặc chưa được phép bỏ qua.
- [ ] Nếu chấp nhận kết quả partial, có bộ đếm lỗi, danh sách lỗi phù hợp và trạng thái **PARTIAL**.
- [ ] Nếu dừng sớm, có trạng thái **STOPPED_EARLY** hoặc lý do dừng rõ ràng.
- [ ] Lỗi của callback ứng dụng được xử lý tại callback hoặc ném ra caller; không trông chờ `visitFileFailed` tự hứng toàn bộ.
- [ ] Đã phân biệt chế độ không theo symbolic link với `FOLLOW_LINKS`; có giới hạn độ sâu và policy vòng nếu cần.
- [ ] Không hardcode thứ tự directory entries vào unit test.
- [ ] Dùng `try-with-resources`/`finally` đúng phạm vi cho tài nguyên ứng dụng.
- [ ] Có test cho thiếu file tùy chọn, quyền bị từ chối, lỗi directory, skip nhánh, skip siblings, terminate và lỗi từ callback.
- [ ] Không dùng thư mục thật có dữ liệu người dùng cho bài test xóa.
- [ ] Đã ghi rõ kiến thức hiện hành: `Files.walkFileTree`, `FileVisitor`, `SimpleFileVisitor`, `FileVisitResult` có từ Java 7; `Files.writeString`/`Path.of` trong chương trình có từ Java 11 và chạy trên Java 17+.

## 21. Kết luận

Trong Java NIO.2, **`Files.walkFileTree`** cho phép kiểm soát quá trình duyệt một cây tệp qua các callback của `FileVisitor`. `SKIP_SUBTREE` bỏ **nội dung của một nhánh**, `SKIP_SIBLINGS` bỏ **những entry cùng cấp còn lại**, còn `TERMINATE` dừng **toàn bộ traversal**. Lỗi file được xử lý qua `visitFileFailed`; lỗi liệt kê nội dung thư mục có thể đến qua `postVisitDirectory(dir,exc)`; lỗi do **chính callback ứng dụng** ném cần được xử lý tại chỗ hoặc truyền tới caller.

Quan trọng nhất là **giữ đúng ngữ nghĩa kết quả**: bỏ qua một file không đồng nghĩa xử lý file đó thành công; dừng sớm không đồng nghĩa đã quét toàn bộ cây; trả `CONTINUE` sau lỗi phải đi kèm chính sách báo cáo tính đầy đủ. Những nguyên tắc Java 7 này vẫn áp dụng trong các hệ thống Java hiện đại, giúp viết các công cụ tìm tệp, lập chỉ mục, sao lưu và quét thư mục an toàn hơn, dễ kiểm thử hơn.