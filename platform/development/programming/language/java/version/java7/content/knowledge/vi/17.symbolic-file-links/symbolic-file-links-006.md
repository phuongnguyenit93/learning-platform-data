# Java 7 — Liên kết tệp: Chính sách sao chép, di chuyển hoặc xóa liên kết

## 1. Mục tiêu bài học

Trong Java NIO.2, một `Path` có thể trỏ tới **file thường**, **thư mục**, **symbolic link** hoặc một tên tệp có nhiều **hard link** cùng tham chiếu đến một đối tượng lưu trữ. Khi sao chép, di chuyển hoặc xóa, hành vi đối với *tên liên kết* và *đối tượng đích* khác nhau đáng kể. Nhầm lẫn có thể dẫn đến:

- Sao chép **nội dung của file đích** trong khi muốn sao chép **symbolic link**.
- Di chuyển một symbolic link sang thư mục khác, khiến **đường dẫn tương đối lưu trong link bị hỏng**.
- Xóa nhầm file thật vì tự giải quyết link rồi xóa đường dẫn đã được resolve.
- Dùng `Files.exists(path)` rồi nghĩ một **dangling symlink** không tồn tại và không cần dọn.
- Duyệt cả cây bằng `Files.walkFileTree` nhưng quên xác định chính sách có theo link hay không.
- Tin rằng thao tác `copy/move/delete` tự động atomic, portable và không bao giờ đụng vào dữ liệu ngoài thư mục cho phép.

Mục tiêu là hiểu đúng **chính sách sao chép, di chuyển và xóa liên kết** bằng các API còn áp dụng hiện nay trên **Java 17+**:

- `Files.copy` và `LinkOption.NOFOLLOW_LINKS`.
- `StandardCopyOption.REPLACE_EXISTING` và `COPY_ATTRIBUTES`.
- `Files.move` và `StandardCopyOption.ATOMIC_MOVE`.
- `Files.delete` / `Files.deleteIfExists`.
- `Files.createSymbolicLink`, `Files.readSymbolicLink`, `Files.isSymbolicLink`.
- `Files.createLink` (hard link) và `Files.isSameFile`.
- `Files.exists(path, NOFOLLOW_LINKS)`, `Files.walkFileTree` và giới hạn bảo mật.

Những API này thuộc **Java 7 NIO.2** và tiếp tục được hỗ trợ trên JDK hiện đại. Ví dụ chính sử dụng thêm `Path.of` và `Files.writeString/readString` (có từ Java 11), nên yêu cầu **Java 17+**; không cần chạy lại JDK 7 hoặc dựa vào kiến thức đã lỗi thời.

## 2. Hai loại liên kết phải phân biệt trước khi thao tác

### 2.1. Symbolic link — một entry chứa đường dẫn tới đích

Symbolic link (symlink, liên kết tượng trưng) là một entry trong filesystem lưu một **đường dẫn mục tiêu**. Đường dẫn đó có thể là absolute hoặc relative, và không nhất thiết phải trỏ tới một đối tượng hiện đang tồn tại.

```text
work/
├── target.txt       (file thật, nội dung "original")
└── shortcut.txt     (symbolic link, target-path = "target.txt")
                           │
                           └── giải nghĩa relative từ work/
                                → work/target.txt
```

Nếu ứng dụng mở `work/shortcut.txt` để đọc **theo link**, filesystem có thể truy cập nội dung của `work/target.txt`. Nhưng **chính entry `shortcut.txt` vẫn là một đối tượng riêng** với đường dẫn đích lưu bên trong.

Một symbolic link có thể trở thành **dangling/broken symlink** khi mục tiêu không tồn tại. Ví dụ `shortcut.txt` chứa target-path `"missing.txt"` nhưng file `missing.txt` chưa được tạo.

### 2.2. Hard link — một tên khác cho cùng đối tượng file

Hard link là một **directory entry khác** tham chiếu tới cùng đối tượng file:

```text
work/
├── target.txt  ──────┐
└── hard.txt    ──────┴──► cùng đối tượng dữ liệu file
```

Trên filesystem hỗ trợ hard link, hai tên có thể cùng trỏ tới **chính một file vật lý/logical file identity**. Cả hai là tên truy cập bình đẳng; không có một nội dung trung gian dạng target-path như symbolic link.

Hệ quả:

- `Files.isSymbolicLink(hardPath)` thông thường trả `false`.
- `Files.isSameFile(hardPath, targetPath)` thường trả `true` nếu hai tên trỏ cùng file.
- Ghi nội dung qua một tên cũng thay đổi nội dung quan sát qua tên kia.
- Xóa một tên hard link chỉ xóa **directory entry đó**; nếu tên khác vẫn tồn tại thì dữ liệu có thể tiếp tục truy cập qua tên còn lại.
- Số lượng hard link, quy tắc tạo trên thư mục, qua volume và quyền cần thiết là **filesystem-specific**.

**Không đồng nhất hard link với một symbolic link dùng `NOFOLLOW_LINKS`.** Đối với API chung, hard link được truy cập như một file thường; nó không mang một chuỗi đường dẫn đích để `readSymbolicLink` trả về.

### 2.3. Một Path không tự cho biết loại entry

`Path.of("work", "shortcut.txt")` chỉ tạo đối tượng Path. Nó **không truy cập filesystem**, không nói entry là symlink hay file thường, cũng không bảo đảm tồn tại. Khi thao tác, phải gọi API `Files` và chọn chính sách theo symbolic link cho đúng mục đích.

## 3. Ma trận chính sách — điều quan trọng nhất

Giả sử `link` là một symbolic link hợp lệ tới `target`; `destination` chưa tồn tại, trừ khi có ghi chú khác.

| Lệnh | Thao tác với symbolic link nguồn | Điều gì xảy ra với file đích của link? |
| --- | --- | --- |
| `Files.copy(link, destination)` | Theo link, sao chép **đối tượng cuối cùng được trỏ tới**, ví dụ nội dung file thường | File gốc không bị di chuyển/xóa; destination thường là file mới độc lập |
| `Files.copy(link, destination, NOFOLLOW_LINKS)` | Sao chép **chính symbolic link** nếu provider hỗ trợ | Không sao chép nội dung target; link mới có thể vẫn trỏ tới target-path cũ |
| `Files.move(link, destination)` | Di chuyển/đổi tên **chính link entry** | File target không bị di chuyển |
| `Files.delete(link)` | Xóa **chính link entry** | File target không bị xóa |
| `Files.deleteIfExists(link)` | Xóa entry link nếu nó tồn tại | Target không bị xóa |
| `Files.copy(source, link, REPLACE_EXISTING)` | Nếu `link` là **đường dẫn đích đã có**, thay thế **link entry ở đích** | File mà link ở đích từng trỏ tới không bị ghi đè chỉ vì option này |
| `Files.exists(link)` | Mặc định **theo link** để kiểm tra | Broken link thường trả `false` |
| `Files.exists(link, NOFOLLOW_LINKS)` | Kiểm tra **entry link** | Broken link vẫn có thể trả `true` |

**Phân biệt chiều:** Trong `Files.copy(source, target, options)`, `source` và `target` có vai trò khác nhau. `NOFOLLOW_LINKS` xác định **cách xử lý symlink phía nguồn** khi sao chép. `REPLACE_EXISTING` quyết định điều gì xảy ra nếu **đường dẫn đích đã tồn tại**, và nếu đích là symlink thì thay **chính link ở đích**, không ghi đè file mà nó trỏ tới.

Đây là hợp đồng của Java SE 17 NIO API. Khi provider không hỗ trợ symbolic links hoặc một option, có thể nhận `UnsupportedOperationException`/`IOException` thay vì kết quả thành công.

## 4. Tạo symbolic link và hiểu đường dẫn mục tiêu

### 4.1. createSymbolicLink có thể lưu đường dẫn tương đối

```java
Path directory = Path.of("work");
Path target = directory.resolve("target.txt");
Path link = directory.resolve("shortcut.txt");

Files.createSymbolicLink(link, Path.of("target.txt"));
```

Đây là **snippet trong phương thức** với imports `java.nio.file.Path`, `java.nio.file.Files` và xử lý `IOException`/các lỗi không hỗ trợ. `Files.createSymbolicLink` là thao tác **tùy chọn**, có thể không được filesystem/provider hoặc quyền hiện tại cho phép.

Đối số đầu là **tên entry link cần tạo**; đối số thứ hai là **đường dẫn được lưu làm target**. Nếu target-path là relative, nó được giải nghĩa tương đối với **thư mục chứa link**, không phải mặc định tương đối với working directory của process khi về sau mở link.

Nghĩa là:

```text
Link:   work/shortcut.txt
Target lưu trong link: target.txt
Target được hiểu:     work/target.txt
```

Nếu file `work/target.txt` chưa tồn tại, provider có thể vẫn cho phép tạo symlink; lúc đó link bị dangling.

### 4.2. readSymbolicLink không phải toRealPath

```java
Path storedTarget = Files.readSymbolicLink(link);
System.out.println(storedTarget);
```

Đây là snippet trong phương thức, `link` phải là symbolic link, có xử lý IOException. Với ví dụ trên, `storedTarget` có thể là Path relative `target.txt`. API đọc **đường dẫn được lưu trong link**, không tự truy tìm và xác minh file cuối cùng. Ngược lại, `toRealPath()` (không có `NOFOLLOW_LINKS`) yêu cầu đường dẫn tồn tại và giải quyết các link theo hợp đồng provider, có thể ném `IOException`.

Nếu muốn mô tả **ứng viên đích được giải nghĩa về mặt lexical** của link relative, có thể dùng:

```java
Path storedTarget = Files.readSymbolicLink(link);
Path lexicalTarget = storedTarget.isAbsolute()
        ? storedTarget
        : link.getParent().resolve(storedTarget).normalize();
```

Đây là snippet trong phương thức, giả định `link.getParent() != null`. **Không** coi `lexicalTarget` là đường dẫn thực hoặc kiểm tra bảo mật: symlink có thể lồng nhiều tầng, bị thay đổi, và `normalize()` chỉ xử lý cú pháp. Với link không có parent, cần quyết định một đường cơ sở phù hợp trước khi resolve.

### 4.3. Không thể suy support chỉ từ tên OS

Trên Windows, quyền tạo symlink có thể phụ thuộc cấu hình hệ thống, quyền process, loại target; trên Linux, quyền parent directory/provider vẫn có thể chặn; ZIP filesystem có thể không hỗ trợ. Nên xử lý `FileSystemException`, `UnsupportedOperationException` và các ngoại lệ thực tế, thay vì chỉ dùng `System.getProperty("os.name")`.

Khi tạo hard link bằng `Files.createLink(link, existing)`, yêu cầu về cùng filesystem/file store, quyền và loại đối tượng cũng là **tùy chọn/implementation-specific**.

## 5. Files.copy: mặc định theo symbolic link nguồn

Lệnh:

```java
Files.copy(sourceLink, copyPath);
```

nếu `sourceLink` là symbolic link trỏ tới **file thường tồn tại**, mặc định copy **nội dung của file đích cuối cùng** sang một file mới tại `copyPath`. Sau khi copy:

- `Files.isSymbolicLink(copyPath)` thường là `false`.
- `Files.readString(copyPath)` trả nội dung của file gốc ở thời điểm sao chép thành công.
- Thay đổi nội dung của `copyPath` không phải thay đổi một hard link tới file gốc; đừng nhầm sao chép dữ liệu với tạo thêm alias.
- `sourceLink` và file gốc vẫn ở chỗ cũ.

Ví dụ:

```text
Trước:
target.txt    ("original")
shortcut.txt  -> target.txt

Files.copy(shortcut.txt, copy-content.txt)

Sau:
target.txt       ("original")
shortcut.txt     -> target.txt
copy-content.txt ("original")     // file thường, không phải symlink
```

**Trường hợp đích của symlink là thư mục:** `Files.copy` mặc định sao chép đối tượng được trỏ tới, nhưng với nguồn là **thư mục**, một lần `copy` chỉ tạo thư mục đích **rỗng**, không tự sao chép cây con. Muốn copy toàn bộ cây phải dùng cơ chế duyệt và một chính sách link cụ thể.

**Trường hợp symlink bị dangling:** mặc định copy sẽ thử theo link đến một target không tồn tại, vì vậy có thể ném `NoSuchFileException`/`IOException`. Điều đó khác với copy **link entry** bằng `NOFOLLOW_LINKS`.

### 5.1. Copy không phải transaction

Ngay cả với source file thường, `Files.copy` không được bảo đảm là thao tác atomic. Khi IOException xuất hiện, file đích có thể đã được tạo nhưng chưa có đủ nội dung hoặc metadata. Không coi “copy thất bại” là “đích chắc chắn chưa thay đổi”.

Nếu phần mềm cần bản sao đáng tin cậy, thiết kế checksum/integrity check, file tạm, cleanup/retry và chính sách publish phù hợp. `COPY_ATTRIBUTES` cũng không làm thao tác copy trở thành atomic.

## 6. Files.copy với NOFOLLOW_LINKS: sao chép chính link

Khi bạn muốn bản sao là một symbolic link thay vì file chứa nội dung đích:

```java
Files.copy(sourceLink, destinationLink, LinkOption.NOFOLLOW_LINKS);
```

`LinkOption.NOFOLLOW_LINKS` thực hiện giao diện `CopyOption` nên có thể truyền vào `Files.copy(Path, Path, CopyOption...)`. Theo Javadoc, nếu source là symlink và provider hỗ trợ, lệnh sao chép **chính symlink**; nó không theo target để lấy nội dung.

Ví dụ:

```text
Trước:
work/
  target.txt
  shortcut.txt -> target.txt

Files.copy(shortcut.txt, copy-shortcut.txt, NOFOLLOW_LINKS)

Sau:
work/
  target.txt
  shortcut.txt      -> target.txt
  copy-shortcut.txt -> target.txt
```

Sao chép link **không tạo bản sao nội dung của file đích**. Hai symlink có thể cùng trỏ tới target đang có. Nếu target biến mất, cả hai link có thể trở thành dangling.

### 6.1. Chuyển link sang một thư mục khác có thể làm hỏng relative target

Đây là tình huống dễ gây lỗi:

```text
Trước:
data/
  target.txt
  links/
    a.txt -> ../target.txt

Copy a.txt thành:
backup/a.txt -> ../target.txt
```

Đường dẫn `../target.txt` trong link mới được giải nghĩa từ **backup/**. Nếu `backup/../target.txt` không tồn tại, link sao chép sẽ **bị hỏng**, dù link gốc hoạt động. Không giả định `Files.copy(..., NOFOLLOW_LINKS)` sẽ tự viết lại đường dẫn tương đối để “giữ ý nghĩa logic” của link trong cấu trúc thư mục mới.

**Lựa chọn thiết kế:** nếu muốn bảo toàn ý nghĩa trỏ tới một target thật sau khi di chuyển/copy sang root mới, cần một chiến lược **rebase** liên kết: xác định target theo chính sách an toàn, tạo đường dẫn mới có ý nghĩa tại thư mục đích, kiểm tra provider/quyền, và tránh rủi ro mở path do input không tin cậy. Không tùy tiện convert mọi link thành absolute path vì có thể phá tính portable khi triển khai sang máy khác.

### 6.2. COPY_ATTRIBUTES không chắc áp dụng cho symlink

```java
Files.copy(sourceLink, destinationLink,
        LinkOption.NOFOLLOW_LINKS,
        StandardCopyOption.COPY_ATTRIBUTES);
```

`COPY_ATTRIBUTES` cố gắng sao chép thuộc tính file theo hỗ trợ của provider; khi sao chép **chính symlink**, tài liệu nêu việc copy các thuộc tính link là implementation-specific và option này có thể được bỏ qua. Không hứa timestamp, ACL, user xattrs hoặc quyền được giữ nguyên trên mọi filesystem.

## 7. REPLACE_EXISTING: phải phân biệt symlink ở đích

Giả sử:

```text
target.txt ("original")
replace-me.txt -> target.txt
new-source.txt ("new")
```

Gọi:

```java
Files.copy(newSource, replaceMe, StandardCopyOption.REPLACE_EXISTING);
```

Theo hợp đồng `Files.copy`, nếu **đường dẫn đích** `replaceMe` là symlink thì **chính entry link bị thay thế**, không phải file `target.txt` mà link từng trỏ tới.

Sau khi thành công:

```text
target.txt      ("original")   // không bị sửa vì REPLACE_EXISTING
replace-me.txt  ("new")        // một regular file thay cho symlink cũ
new-source.txt  ("new")
```

Đây là điểm đặc biệt quan trọng khi phân biệt **source symlink** với **target symlink**. Theo mặc định, symlink ở **source** được copy theo đến nội dung cuối; nhưng nếu đang **ghi đè target path là symlink**, `REPLACE_EXISTING` thay **link entry ở target path**.

### 7.1. Nếu không có REPLACE_EXISTING?

Khi path đích đã tồn tại, `Files.copy` mặc định thất bại (trừ một số trường hợp source và target là cùng file theo hợp đồng). Một `FileAlreadyExistsException` có thể được ném. Đừng gọi `Files.exists(target)` rồi quyết định copy không bảo vệ, vì trạng thái có thể thay đổi giữa check và copy.

### 7.2. Không dùng REPLACE_EXISTING làm sandbox bảo mật

Dù `REPLACE_EXISTING` có quy tắc rõ về target symlink **ở entry cuối**, path vẫn có thể chứa các **thư mục cha là symlink** hoặc bị sửa trong lúc thao tác. Quyền, root, filesystem provider và TOCTOU race cần kiểm soát ở mức hệ thống. Không tự coi `REPLACE_EXISTING` là biện pháp chống path traversal.

### 7.3. Không thay symlink trỏ tới thư mục bằng logic xóa thư mục

Nếu target path là **directory không rỗng**, `REPLACE_EXISTING` không có quyền “xóa sạch cây” để thay thế. Cần phân biệt directory thật với **symbolic link tới directory**: link entry có thể được thay thế trong khi directory gốc vẫn còn nguyên. Mọi thao tác xóa cây là một nghiệp vụ riêng và đòi hỏi chính sách an toàn rất chặt.

## 8. Files.move: di chuyển link entry, không di chuyển file đích

Với symlink nguồn, lời gọi:

```java
Files.move(oldLink, newLink);
```

**di chuyển/đổi tên chính symlink**, không di chuyển file mà nó trỏ tới. Đây là hành vi mặc định, **không cần** truyền `NOFOLLOW_LINKS` vào `move`.

Ví dụ:

```text
Trước:
target.txt
shortcut.txt -> target.txt

Files.move(shortcut.txt, moved-shortcut.txt)

Sau:
target.txt
moved-shortcut.txt -> target.txt
shortcut.txt không còn
```

Nếu move link trong **cùng thư mục**, relative target có thể tiếp tục hợp lệ. Nếu chuyển **sang thư mục khác**, relative target sẽ được hiểu từ thư mục mới; link có thể trở thành dangling. **Việc di chuyển symlink không đồng nghĩa tự rebasing target path.**

### 8.1. Tùy chọn REPLACE_EXISTING khi move

```java
Files.move(oldLink, newLink, StandardCopyOption.REPLACE_EXISTING);
```

Cho phép thay entry đích nếu thích hợp và provider hỗ trợ; nếu đích là symbolic link, tài liệu nêu thay **chính symlink ở đích**, không phải file mà nó trỏ tới. Nếu đích là thư mục không rỗng, không được mặc định thay thế thành công.

**Không suy rằng move thành công nếu source/target nằm trên hai filesystem khác nhau.** Với cross-provider hoặc cross-file-store moves, thao tác có thể yêu cầu copy/delete, có giới hạn về atomicity và rollback.

### 8.2. ATOMIC_MOVE: một mục tiêu riêng với giới hạn cụ thể

```java
Files.move(oldLink, newLink, StandardCopyOption.ATOMIC_MOVE);
```

`ATOMIC_MOVE` yêu cầu hệ thống tệp thực hiện **atomic file-system operation**. Nếu không hỗ trợ trong trường hợp cụ thể, có thể ném `AtomicMoveNotSupportedException`. Khi option này có mặt, các option khác **bị bỏ qua theo hợp đồng**, và hành vi với target đã tồn tại có thể **implementation-specific**.

Không khẳng định:

- Mọi filesystem hỗ trợ atomic move.
- Move qua volume/network provider luôn atomic.
- Atomic move tự động đồng bộ dữ liệu và thư mục để chống mọi kiểu crash.
- Atomic move cho symbolic link tự động sửa đường dẫn tương đối đã lưu.
- Move thành công nghĩa là mọi ứng dụng đọc file đã được đồng bộ tức thời.

Đối với dữ liệu quan trọng, phải thiết kế tính nguyên tử của bước publish, durability và chính sách recovery phù hợp với **file store thực tế**.

### 8.3. Nếu move thất bại

Theo Javadoc, khi move không phải atomic và gặp IOException, trạng thái source/target có thể chưa được xác định trọn vẹn: file có thể đã di chuyển một phần hoặc các thuộc tính chưa được chuyển hết. Với link, phải kiểm tra lại **entry cụ thể** sau lỗi, không tự retry vô điều kiện làm ghi đè các tên khác.

## 9. Files.delete và deleteIfExists: xóa link, không xóa target

Lệnh:

```java
Files.delete(link);
```

nếu `link` là symbolic link, nó xóa **chính entry liên kết**, **không** xóa file đích cuối của link. `Files.deleteIfExists(link)` có cùng quy tắc nhưng trả boolean khi link entry có hay không.

```text
Trước:
target.txt ("original")
shortcut.txt -> target.txt

Files.delete(shortcut.txt)

Sau:
target.txt ("original")
shortcut.txt không tồn tại
```

**Cảnh báo:** Nếu ứng dụng tự gọi `link.toRealPath()` rồi `Files.delete(realTarget)`, lúc này nó đang yêu cầu **xóa target**, không còn là xóa symbolic link. Đây là một bug có thể dẫn tới mất dữ liệu nghiêm trọng.

### 9.1. deleteIfExists với dangling symlink

Một liên kết hỏng vẫn là **entry tồn tại trên filesystem**, dù target không tồn tại:

```java
Path dangling = root.resolve("dangling.txt");

System.out.println(Files.exists(dangling)); // Có thể false nếu target không có
System.out.println(Files.exists(dangling,
        LinkOption.NOFOLLOW_LINKS));           // true nếu link entry có
System.out.println(Files.deleteIfExists(dangling)); // true khi xóa được link
```

Đây là snippet trong phương thức với `Path root` đã khai báo và `dangling` thật sự là symlink bị hỏng, xử lý IOException. `Files.exists(path)` **mặc định theo link**; nó trả `false` nếu không xác định được target. `Files.exists(path, NOFOLLOW_LINKS)` kiểm tra **entry cuối** nên có thể trả true cho symlink bị hỏng.

**Không cần theo target để xóa symbolic link.** Nếu muốn dọn các symlink bị hỏng, hãy nhận diện entry bằng `Files.isSymbolicLink` hoặc đọc thuộc tính với `NOFOLLOW_LINKS`, rồi xóa đúng Path của entry.

### 9.2. Deleting symlink tới thư mục

Nếu một symbolic link trỏ tới **thư mục có nhiều file**, `Files.delete(link)` xóa **link**, không đệ quy xóa thư mục mà nó trỏ tới. Ngược lại, `Files.delete(actualDirectory)` chỉ thành công khi thư mục trống theo quy tắc filesystem; đừng nghĩ API delete sẽ recursive.

### 9.3. Delete có thể thất bại

Một số OS/provider không cho xóa file đang mở, thiếu quyền, hoặc có race. `Files.delete` ném `IOException`; `deleteIfExists` không tự biến mọi lỗi I/O thành `false`. Cả hai cũng không được bảo đảm atomic đối với mọi hoạt động filesystem. Luôn xử lý lỗi và tránh nuốt exception trong workflow dữ liệu quan trọng.

## 10. Hard link: di chuyển/xóa một tên không giống xóa mọi tên

Tạo hard link khi filesystem hỗ trợ:

```java
Path original = Path.of("work", "target.txt");
Path alias = Path.of("work", "hard.txt");

Files.createLink(alias, original);
```

Đây là snippet trong phương thức, giả sử `original` tồn tại; cần import Files/Path và xử lý IOException/unsupported. `Files.createLink` là **optional operation**; hầu hết filesystem đòi các link của một file nằm trên **cùng file store**. Một số OS hạn chế hard link tới directory và yêu cầu quyền nhất định.

Khi tạo thành công:

```java
System.out.println(Files.isSameFile(original, alias)); // thường true
```

`Files.isSameFile` là một phép kiểm tra danh tính file thực, **khác** so sánh `Path.equals`. Nó có thể cần I/O và ném IOException. Đừng áp giả định này khi nguồn/đích không còn tồn tại hoặc provider không cung cấp hard link semantics.

### 10.1. Xóa một tên hard link

```java
Files.delete(original);
String stillThere = Files.readString(alias);
```

Nếu `alias` vẫn là một hard link đến cùng dữ liệu, xóa `original` chỉ xóa **tên directory entry** đó; `alias` vẫn cho phép đọc nội dung. Không còn khái niệm “target-path được lưu trong link” như symbolic link.

Một số hệ thống chỉ giải phóng dữ liệu thực sự sau khi **không còn tên tham chiếu và không còn handle đang mở**, theo semantics OS. Không dùng suy luận `Files.exists(original) == false` để kết luận toàn bộ nội dung dữ liệu không còn khả dụng nếu còn các hard link khác.

### 10.2. Move hard link

`Files.move(alias, renamedAlias)` di chuyển/đổi tên **directory entry** đó. Những tên hard link khác (nếu còn) không tự bị đổi tên. Nếu bạn muốn biết hai path có là cùng file sau một lượt thao tác, hãy dùng `Files.isSameFile` khi thích hợp và xử lý race.

### 10.3. Copy hard link

Với `Files.copy(alias, another)`, source là một **file bình thường qua tên alias**, không phải một symlink. Sao chép dữ liệu thường tạo một file đích riêng, **không mặc định bảo toàn topology hard links**. `NOFOLLOW_LINKS` không biến hard link thành một metadata link cần copy như symlink.

Nếu backup cần **giữ các quan hệ hard link** để không nhân bản dữ liệu/giữ danh tính, cần công cụ/format backup hiểu hard links, kiểm tra file identity và khả năng của filesystem đích; không trông đợi một vòng lặp `Files.copy` đơn giản tự duy trì topology.

### 10.4. Hard link tới symbolic link có ngữ nghĩa tùy provider

Javadoc `Files.createLink(link, existing)` lưu ý nếu `existing` là **symbolic link**, việc hard link gắn tới chính symlink hay tới target có thể **phụ thuộc nền tảng**. Tránh phụ thuộc hành vi này trong mã portable. Ví dụ chính chỉ tạo hard link trực tiếp tới **regular file**.

## 11. Ví dụ Java 17+ hoàn chỉnh và được kiểm thử trên hai môi trường

Chương trình sau tạo một thư mục tạm riêng, tạo file `target.txt`, sau đó:

1. **Thử** tạo symbolic link tương đối. Nếu quyền/provider không cho phép, thông báo bỏ qua nhánh symbolic.
2. Nếu được, thử copy mặc định, copy với NOFOLLOW, move, delete, dangling link và REPLACE_EXISTING đích là symlink.
3. Thử tạo hard link. Nếu có, kiểm tra same-file, xóa tên gốc và đổi tên hard link.
4. Dọn những entry được tạo trong **chính thư mục tạm**; không tác động file dự án hoặc file người dùng.

Tạo tệp **`LinkPolicyDemo.java`**:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileSystemException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.DirectoryStream;

public class LinkPolicyDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("link-policy-demo-");
        Path target = root.resolve("target.txt");
        Files.writeString(target, "original", StandardCharsets.UTF_8);

        try {
            Path link = root.resolve("shortcut.txt");
            boolean symbolicSupported;
            try {
                Files.createSymbolicLink(link, Path.of("target.txt"));
                symbolicSupported = true;
            } catch (UnsupportedOperationException | FileSystemException
                     | SecurityException unsupported) {
                symbolicSupported = false;
            }

            System.out.println("symbolic links available = " + symbolicSupported);
            if (symbolicSupported) {
                Path copiedFile = root.resolve("copy-content.txt");
                Files.copy(link, copiedFile);
                System.out.println("default copy is symbolic = " +
                        Files.isSymbolicLink(copiedFile));
                System.out.println("default copy content = " +
                        Files.readString(copiedFile, StandardCharsets.UTF_8));

                Path copiedLink = root.resolve("copy-shortcut.txt");
                Files.copy(link, copiedLink, LinkOption.NOFOLLOW_LINKS);
                System.out.println("nofollow copy is symbolic = " +
                        Files.isSymbolicLink(copiedLink));
                System.out.println("nofollow target = " +
                        Files.readSymbolicLink(copiedLink));

                Path moved = root.resolve("moved-shortcut.txt");
                Files.move(link, moved);
                System.out.println("moved entry is symbolic = " +
                        Files.isSymbolicLink(moved));
                System.out.println("old entry removed = " +
                        !Files.exists(link, LinkOption.NOFOLLOW_LINKS));
                Files.delete(moved);
                System.out.println("delete link keeps target = " +
                        Files.readString(target, StandardCharsets.UTF_8).equals("original"));

                Path dangling = root.resolve("dangling.txt");
                Files.createSymbolicLink(dangling, Path.of("missing.txt"));
                System.out.println("dangling followed exists = " +
                        Files.exists(dangling));
                System.out.println("dangling nofollow exists = " +
                        Files.exists(dangling, LinkOption.NOFOLLOW_LINKS));
                System.out.println("dangling delete = " +
                        Files.deleteIfExists(dangling));

                Path replacement = root.resolve("replacement.txt");
                Files.createSymbolicLink(replacement, Path.of("target.txt"));
                Path source = root.resolve("source.txt");
                Files.writeString(source, "new", StandardCharsets.UTF_8);
                Files.copy(source, replacement, StandardCopyOption.REPLACE_EXISTING);
                System.out.println("replaced link now regular = " +
                        Files.isRegularFile(replacement, LinkOption.NOFOLLOW_LINKS));
                System.out.println("replacement kept original target = " +
                        Files.readString(target, StandardCharsets.UTF_8).equals("original"));
            } else {
                System.out.println("symbolic operations = skipped");
            }

            Path hard = root.resolve("hard.txt");
            boolean hardSupported;
            try {
                Files.createLink(hard, target);
                hardSupported = true;
            } catch (UnsupportedOperationException | FileSystemException
                     | SecurityException unsupported) {
                hardSupported = false;
            }
            System.out.println("hard links available = " + hardSupported);
            if (hardSupported) {
                System.out.println("hard link same file = " +
                        Files.isSameFile(hard, target));
                Files.delete(target);
                System.out.println("hard survives source deletion = " +
                        Files.readString(hard, StandardCharsets.UTF_8).equals("original"));
                Path renamed = root.resolve("renamed-hard.txt");
                Files.move(hard, renamed);
                System.out.println("moved hard retains data = " +
                        Files.readString(renamed, StandardCharsets.UTF_8).equals("original"));
            } else {
                System.out.println("hard link operations = skipped");
            }
        } finally {
            try (DirectoryStream<Path> entries = Files.newDirectoryStream(root)) {
                for (Path entry : entries) {
                    Files.deleteIfExists(entry);
                }
            }
            Files.deleteIfExists(root);
        }
    }
}
```

Biên dịch và chạy trên JDK 17+:

```bash
javac --release 17 LinkPolicyDemo.java
java LinkPolicyDemo
```

**Stdout đã kiểm thử trên Linux với OpenJDK 21 biên dịch `--release 17` và filesystem hỗ trợ cả hai loại link:**

```text
symbolic links available = true
default copy is symbolic = false
default copy content = original
nofollow copy is symbolic = true
nofollow target = target.txt
moved entry is symbolic = true
old entry removed = true
delete link keeps target = true
dangling followed exists = false
dangling nofollow exists = true
dangling delete = true
replaced link now regular = true
replacement kept original target = true
hard links available = true
hard link same file = true
hard survives source deletion = true
moved hard retains data = true
```

**Stdout đã kiểm thử trên môi trường Windows với JDK 24, nơi lần thử tạo symbolic link không được phép nhưng hard link hoạt động:**

```text
symbolic links available = false
symbolic operations = skipped
hard links available = true
hard link same file = true
hard survives source deletion = true
moved hard retains data = true
```

Trên môi trường **không hỗ trợ hard link hoặc thiếu quyền tạo hard link**, nhánh cuối có thể là:

```text
hard links available = false
hard link operations = skipped
```

Hai nhánh symbolic/hard được **phát hiện qua thao tác thử tạo trong file tạm**, không hard-code từ tên OS. Trong demo, một lỗi `FileSystemException` ở bước tạo link được diễn giải là “không tạo được link trong môi trường thử”, **không phải chứng minh provider vĩnh viễn không hỗ trợ tính năng** — có thể là quyền, chính sách hoặc lỗi storage. Những `IOException` khác từ quá trình copy/move/delete vẫn có thể được báo ra; code không âm thầm nuốt lỗi làm mất dữ liệu. Đây là chương trình học và không phải một mô-đun quản lý link production chống mọi race.

### 11.1. Vì sao dùng DirectoryStream trong finally?

Chương trình biết rõ mình vừa tạo **thư mục tạm ngẫu nhiên** và chỉ tạo các file/symlink/hardlink trực tiếp trong đó. Nó duyệt một cấp bằng `DirectoryStream` rồi xóa từng **entry**, không đệ quy theo symlink tới thư mục ngoài. Điều này đủ cho cleanup của **ví dụ đã kiểm soát nội dung thư mục**.

Không sao chép pattern cleanup này để xóa một directory người dùng cung cấp: thư mục không đáng tin có thể bị thay đổi, chứa symlink, junction/reparse point hoặc tên đặc biệt, và cần một thiết kế riêng để chống race, path traversal và accidental deletion.

### 11.2. Vì sao kiểm tra tồn tại với NOFOLLOW_LINKS sau move?

Sau `Files.move(link, moved)`, source symlink không còn. `Files.exists(link, NOFOLLOW_LINKS)` hỏi **entry**, không hỏi target file, nên phù hợp với mục tiêu xác minh tên link đã được đổi. Với symbolic link bị hỏng, việc không theo link là đặc biệt quan trọng.

### 11.3. Vì sao phần hard link xóa target sau cùng?

Tất cả phép thử symbolic trước đó cần file `target.txt`. Đến phần hard link, chương trình mới xóa một tên gốc và xác minh `hard.txt` vẫn đọc được. Thứ tự giúp phân biệt rõ tác động của hai loại link mà không làm nhiễu kết quả trước đó.

## 12. Một trường hợp dễ quên: symlink đích và symlink nguồn khác nhau

Mỗi lần copy/move hãy viết ra hai câu hỏi:

1. **Source là gì?** Regular file, symbolic link, hard link hay directory?
2. **Target Path hiện là gì?** Chưa tồn tại, regular file, symbolic link hay directory có nội dung?

Nếu source là symlink:

```java
Files.copy(sourceLink, dest); // Mặc định theo link ở source.
```

Nếu target Path hiện là symlink và muốn thay entry:

```java
Files.copy(sourceFile, targetLink,
        StandardCopyOption.REPLACE_EXISTING); // Thay entry ở target.
```

Đừng trộn hai quy tắc này. Về mặt security, cũng phải xét **cha của source và cha của target** có chứa symlink hay không; việc xử lý entry cuối đúng không đủ để xác nhận mọi thành phần path ở mức trên đều đáng tin.

## 13. Duyệt cây tệp: chính sách link khi copy cả thư mục

Một lời gọi `Files.copy(dir, targetDir)` **không** sao chép toàn bộ file con. Muốn copy một cây cần duyệt, ví dụ dùng `Files.walkFileTree` hoặc một công cụ storage có chính sách rõ ràng.

### 13.1. walkFileTree mặc định không theo symlink khi đi xuống cây

```java
Files.walkFileTree(root, visitor);
```

Đây là snippet minh họa có `Path root` và `FileVisitor<Path> visitor`. Mặc định, `walkFileTree` **không theo symbolic links**. Khi gặp một symlink trỏ tới directory, visitor không tự đi vào cây target thông qua symlink đó.

Nếu muốn theo symlink trong traversal, API cho phép `FileVisitOption.FOLLOW_LINKS`, nhưng phải hiểu:

- Có thể gặp **vòng lặp liên kết**.
- Một `FileSystemLoopException` có thể được báo qua callback lỗi.
- Có thể đi ra ngoài cây/root mà người dùng nghĩ mình đang sao chép.
- Traversal không trở thành atomic hay snapshot trong môi trường đồng thời.
- Với dữ liệu không tin cậy, FOLLOW_LINKS có thể gây rủi ro về quyền và phạm vi.

### 13.2. Trap: walkFileTree không theo nhưng Files.copy mặc định lại theo

Giả sử visitor không đi vào symbolic link nhưng tại `visitFile(Path file, ...)` lại gọi:

```java
Files.copy(file, destination);
```

Nếu `file` là symbolic link, **Files.copy mặc định theo source link** để sao chép target. Vì vậy chính sách traversal và chính sách copy **phải phối hợp**.

Nếu mục tiêu là “backup giữ nguyên những symlink có trong cây”, ở nhánh xử lý link cần:

```java
Files.copy(file, destination, LinkOption.NOFOLLOW_LINKS);
```

Đây là snippet minh họa, chỉ sử dụng khi biết source Path thuộc cây cần copy và provider đích hỗ trợ symlink. Còn phải tính lại **relative targets** khi root thư mục nguồn và đích khác nhau, giải quyết lỗi file đã tồn tại, metadata và cleanup.

Nếu mục tiêu là “backup dữ liệu thật theo link”, chỉ theo links **có kiểm soát** trong phạm vi cho phép và có chính sách cycles/giới hạn depth.

### 13.3. Xóa cả cây không mặc nhiên theo link

Với `walkFileTree` mặc định không theo symbolic links, visitor có thể gọi `Files.delete(file)` trên symlink entry và chỉ xóa link. Nhưng nếu bạn bật FOLLOW_LINKS hoặc tự resolve target bằng `toRealPath` rồi xóa, hậu quả có thể khác. Duyệt/xóa cây nhận path không tin cậy cần **security review riêng**, không phải chỉ thêm `NOFOLLOW_LINKS` ở một chỗ là đủ.

## 14. Thuộc tính liên kết và chính sách COPY_ATTRIBUTES

`StandardCopyOption.COPY_ATTRIBUTES` là yêu cầu cố gắng copy metadata:

```java
Files.copy(source, destination,
        StandardCopyOption.COPY_ATTRIBUTES);
```

Với regular file, Javadoc ghi việc copy thuộc tính ngoài các thông tin tối thiểu là **phụ thuộc platform và filesystem**. Khi nguồn là symbolic link nhưng copy có `NOFOLLOW_LINKS`, provider có thể **bỏ qua COPY_ATTRIBUTES** đối với chính symlink.

Đừng mặc định những dữ liệu sau luôn được bảo toàn:

- Owner, group, POSIX mode, ACL.
- Thời gian với độ chính xác nanosecond chính xác như nguồn.
- User-defined extended attributes.
- Định danh file hoặc hard-link topology.
- Các cờ DOS, alternate data streams hoặc metadata của remote filesystem.

Nếu yêu cầu nghiệp vụ **bắt buộc** giữ một số metadata, cần kiểm tra view support, copy xong **read back** và từ chối công bố bản sao hợp lệ khi metadata cần thiết không được duy trì.

### 14.1. Kiểm tra loại entry với LinkOption

```java
boolean isLink = Files.isSymbolicLink(path);

boolean followedRegular = Files.isRegularFile(path);
boolean entryRegular = Files.isRegularFile(path,
        LinkOption.NOFOLLOW_LINKS);
```

Đây là snippet trong phương thức với `Path path`. `Files.isRegularFile(path)` mặc định theo symbolic link khi có thể, nên một symlink tới regular file có thể được nhận là regular file. Dùng `NOFOLLOW_LINKS` để hỏi chính entry. Cả `exists` và các hàm kiểm tra loại đều có thể trả false khi không xác định được trạng thái; nếu cần biết lý do lỗi, dùng `Files.readAttributes` với xử lý `IOException`.

## 15. Bảo mật: symlink traversal, TOCTOU và thao tác ngoài root

Một symlink có thể trỏ ra ngoài thư mục được phép:

```text
allowed/
├── safe.txt
└── shortcut.txt -> ../../outside/secret.txt
```

Nếu ứng dụng nhận `allowed/shortcut.txt` rồi `Files.copy(link, dest)` theo mặc định, nó có thể **đọc dữ liệu ở ngoài allowed/** nếu process có quyền, dù tên symlink nằm trong `allowed/`.

Cũng vậy, `normalize()` chỉ giải quyết tên `.` và `..` theo **lexical path**; nó không giải quyết symbolic links để chứng minh file thực nằm dưới root.

### 15.1. Định nghĩa rõ chính sách với untrusted input

Một chính sách cho ứng dụng upload/backup có thể là:

- **Không cho phép symbolic links** trong vùng nguồn: phát hiện bằng `Files.isSymbolicLink` hoặc thuộc tính NOFOLLOW trước khi mở và tiếp tục kiểm soát race.
- **Giữ nguyên symbolic links nhưng không theo target:** copy entry với NOFOLLOW và đánh giá target-path nếu đích chuyển thư mục.
- **Chỉ theo links trỏ nằm trong allowed root:** cần xác minh target thực và sử dụng thao tác an toàn trước concurrent changes; không dựa vào một lần string prefix check.
- **Cấm hard links tới dữ liệu ngoài phạm vi ownership** nếu threat model yêu cầu: hard links có thể dẫn tới cùng dữ liệu qua một tên bên trong root.
- **Không xóa file theo canonical target path** nếu nghiệp vụ chỉ muốn xóa link entry.

Chính sách phải gắn với **quyền process, ACL, filesystem provider và folder ownership**. Nếu hệ thống cho người dùng thay đổi directory trong lúc xử lý, có nguy cơ *time-of-check/time-of-use (TOCTOU)*: sau khi bạn gọi `Files.isSymbolicLink(path)`, entry có thể bị thay bằng một entry khác trước khi `Files.copy` hoặc `Files.delete`.

### 15.2. SecureDirectoryStream và các thao tác theo handle

`SecureDirectoryStream<Path>` cung cấp những thao tác relative với một directory handle đang mở giúp giảm một số nguy cơ race nếu provider hỗ trợ. Đây là tùy chọn hiện hành của NIO.2, nhưng **không được bảo đảm trên mọi filesystem**; ứng dụng có yêu cầu bảo mật cao phải thiết kế theo khả năng thực tế và xử lý fallback an toàn.

```java
try (DirectoryStream<Path> stream = Files.newDirectoryStream(dir)) {
    if (stream instanceof SecureDirectoryStream<?>) {
        System.out.println("Secure directory operations are available");
    }
}
```

Đây là snippet trong phương thức với imports `DirectoryStream`, `SecureDirectoryStream`, `Files`, `Path`; kết quả **phụ thuộc provider**. Việc nhận được stream loại này không tự bảo vệ những thao tác bên ngoài còn dùng Path/resolve tùy tiện.

### 15.3. Không tự biến việc xóa link thành xóa nội dung

Nếu người dùng yêu cầu “xóa shortcut”, cần thao tác trên **shortcut Path**, không trên target sau `toRealPath()`. Với hard link, xóa tên hard link không giống xóa “bản sao tệp”; dữ liệu có thể vẫn được truy cập bởi một tên khác. Vì vậy UI hoặc API nên dùng thuật ngữ rõ: **xóa liên kết**, **xóa mục tên tệp**, **xóa bản sao dữ liệu** là những ý định khác nhau.

## 16. Khác biệt Windows, Linux, macOS và FileSystem provider

| Yếu tố | Hệ quả khi xử lý links |
| --- | --- |
| Quyền tạo symlink | Windows có thể yêu cầu điều kiện về quyền/cấu hình; Linux/macOS cũng cần quyền filesystem và provider hỗ trợ |
| Hard link | Thường giới hạn trong cùng filesystem/store; một số provider không hỗ trợ; hard link tới directory có thể bị hạn chế |
| Relative symlink | Đường dẫn target tương đối với thư mục chứa link, chuyển link sang vị trí khác có thể làm hỏng |
| Directory symlink / junction | Windows có các loại reparse point; không đồng nhất mọi loại link với API symbolic-link portable |
| Case sensitivity | Tuỳ volume/provider, ảnh hưởng cách tên target được resolve |
| Cross-filesystem copy | Sao chép symlink có thể thất bại nếu đích không hỗ trợ; file attributes có thể mất |
| Cross-filesystem move | Không mặc định atomic; có thể lỗi hoặc cần copy/delete tùy provider |
| Open file deletion | Một số OS không cho xóa file đang được process sử dụng |
| Permission/ACL | Tạo/copy/move/delete link và target có thể yêu cầu quyền khác nhau |

Dùng `Path` và `Files` thay vì nối path bằng dấu `/` hoặc `\` thủ công. Tuy nhiên, **API chung không đồng nghĩa mọi file store có cùng semantics**. Unit test nên chạy trên filesystem thực của môi trường triển khai, không chỉ dựa trên kết quả từ một máy phát triển.

Nếu source Path thuộc ZIP/remote FileSystem và destination thuộc provider khác, không chuyển `source.toString()` thành `Path.of(...)` rồi tưởng giữ được filesystem identity. Mỗi Path thuộc một provider; `Files.copy` có hỗ trợ copy cross-provider theo hợp đồng nhất định, nhưng không bảo đảm giữ nguyên topology link/metadata.

## 17. Lỗi và ngoại lệ cần xử lý

| Trường hợp | Ngoại lệ/hành vi thường gặp | Điều cần làm |
| --- | --- | --- |
| Tạo symlink bị cấm/không hỗ trợ | `UnsupportedOperationException`, `FileSystemException` hoặc lỗi quyền | Báo không thể tạo, không silently thay bằng copy nếu chính sách cần symlink |
| Tạo hard link không hỗ trợ hoặc khác file store | `UnsupportedOperationException`/`IOException` | Thay chính sách hoặc báo lỗi, không giả định link tạo thành |
| Đọc target của Path không phải symlink | `NotLinkException` (optional specific exception)/`IOException` | Xác minh loại entry khi cần, xử lý race |
| Copy symlink mặc định khi target đã mất | `NoSuchFileException`/`IOException` | Cân nhắc NOFOLLOW nếu muốn copy link entry |
| Copy vào target đã tồn tại không REPLACE | `FileAlreadyExistsException` (optional specific exception) | Quyết định policy ghi đè rõ ràng |
| Dùng NOFOLLOW nhưng provider đích không hỗ trợ link | `IOException` hoặc unsupported | Không tự giả vờ tạo thành công |
| Move cần atomic nhưng không được hỗ trợ | `AtomicMoveNotSupportedException` | Fail hoặc fallback có chính sách consistency riêng |
| Delete file/directory không được phép | `AccessDeniedException`/`IOException` | Báo lỗi/thu hồi quyền theo policy; không xóa mục khác thay thế |
| Link/target biến mất giữa check và I/O | `NoSuchFileException`/`IOException` | Xử lý race, tránh retry ghi đè mù quáng |
| Link target tạo cycle | `FileSystemLoopException` khi traversal/real path phù hợp | Áp giới hạn độ sâu và chính sách xử lý vòng |
| Folder đích không rỗng | `DirectoryNotEmptyException`/`IOException` | Không coi REPLACE_EXISTING là lệnh xóa đệ quy |

Một số exception được Javadoc nêu là **optional specific exceptions**: không khẳng định mọi provider trả đúng một subclass. `IOException` là lớp lỗi cần được truyền/ghi nhận với đủ ngữ cảnh. Nếu thao tác thất bại sau khi đã thay đổi filesystem một phần, cần kiểm tra trạng thái thực trước khi retry.

## 18. Chính sách quyết định nên áp dụng cho ứng dụng

### 18.1. Muốn tạo **bản sao dữ liệu thực** từ một symlink

Dùng `Files.copy(link, destination)` với nhận thức rằng **nó theo source link mặc định**. Thực hiện chỉ khi file target nằm trong phạm vi cho phép, kích thước/permission phù hợp và có xử lý lỗi copy một phần.

### 18.2. Muốn backup **chính cấu trúc symlink**

Dùng `Files.copy(link, destination, NOFOLLOW_LINKS)` nếu provider đích hỗ trợ, sau đó đánh giá **relative target** có còn đúng sau khi đổi vị trí hay không. Với backup cây, giữ nhất quán chính sách traverse và copy.

### 18.3. Muốn **đổi tên shortcut**

Dùng `Files.move(link, renamedLink)` trên **link Path**, không cần resolve target. Nếu thay đổi thư mục chứa, kiểm tra lại đường dẫn đích tương đối.

### 18.4. Muốn **xóa shortcut** nhưng giữ file gốc

Dùng `Files.delete(link)` hoặc `Files.deleteIfExists(link)`. Nếu cần xử lý dangling links, hỏi entry với `NOFOLLOW_LINKS` hoặc `Files.isSymbolicLink`.

### 18.5. Muốn thay một file **đích hiện có là symlink**

Dùng `REPLACE_EXISTING` có chủ đích; Javadoc quy định thay link entry ở đích, **không thay file mà link trỏ tới**. Cẩn thận parent symlinks và race.

### 18.6. Muốn giữ quan hệ **hard link** khi backup

Một lệnh copy file không đủ để lưu quan hệ nhiều tên cùng trỏ tới một đối tượng. Cần cơ chế backup nhận diện file identity/hard-link topology và phục hồi có kiểm tra, hoặc chấp nhận rằng file copy là bản dữ liệu độc lập.

## 19. Các sai lầm thường gặp

**1. “Copy symlink mặc định sẽ tạo thêm symlink.”** Sai. Mặc định copy **file đích cuối**; NOFOLLOW mới copy link entry.

**2. “NOFOLLOW_LINKS áp cho Files.move giống Files.copy.”** Không cần dựa vào option đó: move symbolic link **luôn di chuyển chính link** theo hợp đồng.

**3. “Xóa symlink làm mất file thật.”** Sai với `Files.delete(link)`, nhưng **có thể** làm mất file thật nếu ứng dụng tự resolve target rồi xóa sai Path.

**4. “Files.exists(link) false tức tên link không tồn tại.”** Sai với broken symlink; cần `NOFOLLOW_LINKS`.

**5. “Nếu copied symlink tồn tại thì nó sẽ trỏ tới đúng file ban đầu.”** Không chắc; relative target có thể bị hỏng sau khi copy sang thư mục khác.

**6. “REPLACE_EXISTING sẽ ghi đè đích cuối của symlink target.”** Sai. Khi **target path là symlink**, nó thay link entry.

**7. “Files.copy directory sẽ copy luôn mọi file con.”** Sai. Mặc định chỉ tạo directory target rỗng.

**8. “COPY_ATTRIBUTES giữ nguyên mọi metadata của symlink.”** Không; việc copy thuộc tính link tùy provider.

**9. “Files.move với ATOMIC_MOVE luôn thành công trên mọi volume.”** Không. Có thể ném `AtomicMoveNotSupportedException`.

**10. “Atomic move tự sửa đường dẫn symlink tương đối.”** Không; cần kiểm tra target-path sau đổi parent.

**11. “Hard link chính là symlink không theo target.”** Sai. Hard link là tên khác cho cùng đối tượng dữ liệu.

**12. “Xóa tên gốc sẽ xóa dữ liệu dù còn hard link.”** Thường sai; dữ liệu vẫn truy cập qua tên còn lại.

**13. “Files.copy hard link giữ quan hệ hard link.”** Không tự được bảo đảm; copy thường tạo file đích độc lập.

**14. “Hard link giữa nhiều volume luôn được hỗ trợ.”** Không; thường yêu cầu cùng FileStore.

**15. “Files.createLink(existing symlink) luôn hard link target.”** Không; hành vi với existing là symlink phụ thuộc platform.

**16. “walkFileTree không theo link nên Files.copy trong visitor cũng không theo.”** Sai: hai API có **chính sách độc lập**.

**17. “FOLLOW_LINKS trong traversal luôn an toàn.”** Không: có thể theo link ra ngoài root hoặc gặp cycle.

**18. “normalize + startsWith(root) chứng minh mọi file I/O nằm trong root.”** Không: symlink và TOCTOU race chưa được xử lý.

**19. “Tạo được symlink nghĩa là mọi process đều đọc được nó.”** Không; quyền, target availability và provider ảnh hưởng.

**20. “Thấy IOException nghĩa là copy/move chưa chạm gì đến filesystem.”** Không; thao tác có thể đã tạo/ghi một phần.

## 20. Checklist code review

- [ ] Nguồn là file thường, symlink, directory hay hard link? Có kiểm tra đúng loại entry không?
- [ ] Nếu nguồn là symlink, muốn copy **nội dung target** hay **link entry**?
- [ ] Đã chọn `NOFOLLOW_LINKS` đúng cho `Files.copy` nếu cần giữ symlink?
- [ ] Nếu copy/move link sang thư mục khác, target-path **relative** có còn đúng?
- [ ] Nếu path đích tồn tại, `REPLACE_EXISTING` có chủ đích và hiểu nó thay **entry** nào?
- [ ] Có phân biệt source link với target link ở hai phía của `Files.copy`?
- [ ] Nếu move cần atomic, đã xử lý `ATOMIC_MOVE` unsupported và target exists?
- [ ] Nếu copy thất bại giữa chừng, có cleanup, kiểm tra trạng thái và retry an toàn?
- [ ] Nếu xóa link, đã dùng chính Path entry chứ không dùng `toRealPath()` để xóa nhầm target?
- [ ] Có dùng `exists(..., NOFOLLOW_LINKS)` khi cần phát hiện dangling entry?
- [ ] Nếu hard link còn tồn tại, có hiểu xóa một tên không nhất thiết xóa dữ liệu?
- [ ] Nếu backup cần hard-link topology, có cơ chế nhận diện/khôi phục riêng?
- [ ] Nếu copy cây, `walkFileTree` và `Files.copy` có cùng chính sách follow/nofollow?
- [ ] Có giới hạn follow links để tránh cycle và đi ra ngoài root?
- [ ] Có kiểm tra parent directory symlinks/junction và TOCTOU race trong threat model?
- [ ] Có phân biệt `FileAlreadyExistsException`, `NoSuchFileException` và `IOException` khi cần?
- [ ] Có test trên filesystem/volume/permission thực tế (Windows, Linux, remote, ZIP nếu sử dụng)?
- [ ] Có xử lý metadata/ACL/user attributes khi `COPY_ATTRIBUTES` không giữ được?
- [ ] Có dùng link test trong thư mục tạm và cleanup chỉ trong phạm vi của ứng dụng?
- [ ] Có tài liệu hóa rõ “xóa link”, “xóa dữ liệu”, “copy target” và “preserve link” trên API/UI?

## 21. Câu hỏi tự kiểm tra

**1.** `Files.copy(symbolicLink, dest)` mặc định copy gì? — **Nội dung của đối tượng cuối mà link trỏ tới**, không phải link entry.

**2.** Muốn copy chính symbolic link? — Dùng `Files.copy(link, dest, LinkOption.NOFOLLOW_LINKS)` khi provider hỗ trợ.

**3.** `Files.move(link, newPath)` thay target file không? — **Không**, nó di chuyển link entry.

**4.** `Files.delete(link)` có xóa nội dung file đích không? — **Không**, nó xóa link entry.

**5.** Nếu link bị dangling, `Files.exists(link)` có thể ra gì? — **false**, vì mặc định theo link.

**6.** Cách kiểm tra tên của dangling link còn hiện hữu? — `Files.exists(link, NOFOLLOW_LINKS)` hoặc nhận diện bằng `Files.isSymbolicLink`.

**7.** Có thể xóa dangling symlink không? — **Có** bằng `Files.delete/IfExists` trên link entry nếu provider/quyền cho phép.

**8.** `REPLACE_EXISTING` khi destination đã là symlink làm gì? — Thay **chính symlink entry**, không ghi đè target của symlink.

**9.** Relative target được giải nghĩa từ đâu? — Từ **thư mục chứa symlink**.

**10.** Sao chép/move symlink sang thư mục khác có chắc còn trỏ đúng? — **Không**, target relative có thể trở thành dangling.

**11.** `readSymbolicLink(link)` có trả canonical target thật luôn không? — **Không**, nó trả đường dẫn lưu trong link, có thể relative và không tồn tại.

**12.** `Files.createLink(hard, file)` tạo đối tượng gì? — Một **hard link**: tên khác tới cùng file khi filesystem hỗ trợ.

**13.** Xóa `file` sau khi tạo hard link khiến `hard` mất dữ liệu không? — Thông thường **không**, còn truy cập qua `hard`.

**14.** Hard link có `storedTargetPath` giống symlink không? — **Không**.

**15.** `Files.copy(hard, dest)` có bảo toàn topology hard link mặc định không? — **Không**.

**16.** `COPY_ATTRIBUTES` có đảm bảo ACL/user xattrs của symlink được copy không? — **Không**, phụ thuộc provider.

**17.** `Files.copy(directory, dest)` có copy đệ quy không? — **Không**, chỉ tạo thư mục đích rỗng.

**18.** `walkFileTree(root)` mặc định có theo symlink directory không? — **Không**.

**19.** Nếu visitor của walkFileTree gọi `Files.copy(link, dst)` không option, có theo source link không? — **Có**, vì chính sách `Files.copy` mặc định theo link.

**20.** `ATOMIC_MOVE` luôn hoạt động khi source và target khác volume? — **Không**, có thể không được hỗ trợ.

**21.** `normalize()` đủ để chống symlink traversal/race không? — **Không**.

**22.** Trong workflow “xóa shortcut nhưng giữ file”, có nên gọi `delete(link.toRealPath())` không? — **Không**, sẽ nhắm vào target thật.

## Tài liệu chính thức còn áp dụng

- [Java SE 17 — Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): `copy`, `move`, `delete`, `deleteIfExists`, `createSymbolicLink`, `readSymbolicLink`, `createLink`, `exists`, `isSymbolicLink`, `isSameFile`, `walkFileTree`.
- [Java SE 17 — LinkOption](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/LinkOption.html): `NOFOLLOW_LINKS` và vai trò trong CopyOption/OpenOption.
- [Java SE 17 — StandardCopyOption](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardCopyOption.html): `REPLACE_EXISTING`, `COPY_ATTRIBUTES`, `ATOMIC_MOVE`.
- [Java SE 17 — Path](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html): `resolve`, `getParent`, `normalize`, `toRealPath` và ngữ nghĩa đường dẫn.
- [Java SE 17 — FileVisitOption](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileVisitOption.html): `FOLLOW_LINKS` trong duyệt cây tệp.
- [Java SE 17 — SecureDirectoryStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/SecureDirectoryStream.html): thao tác theo directory handle trên provider hỗ trợ để giảm một số race.

**Ghi nhớ:** **`Files.copy` mặc định theo symlink ở nguồn**, **`Files.copy(..., NOFOLLOW_LINKS)` sao chép chính link**, còn **`Files.move` và `Files.delete` tác động lên chính link entry**, không tự thao tác target. **`REPLACE_EXISTING` trên đường dẫn đích là symlink thay chính link đích**. Với hard link, nhiều tên có thể trỏ cùng dữ liệu nên xóa một tên không nhất thiết xóa dữ liệu. Luôn xác định phạm vi, provider/permission, relative target, tính không-atomic và các rủi ro symlink traversal/race trước khi sao chép, di chuyển hoặc xóa.