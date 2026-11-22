# Đọc cây ngoại lệ thay vì chỉ đọc dòng thông điệp cuối trong Java

Trong Java, một thông báo lỗi như `"import failed"` thường chỉ mô tả **thất bại ở tầng đang xử lý**, không phải toàn bộ nguyên nhân. Phía sau một ngoại lệ có thể có chuỗi **`cause`** dẫn tới lỗi kỹ thuật ban đầu, và tại mỗi mắt xích còn có những **`suppressed exceptions`** phát sinh khi đóng tài nguyên hoặc khi hệ thống cố hoàn tất một công việc phụ.

Vì vậy, muốn chẩn đoán chính xác, đừng chỉ đọc một dòng `getMessage()`, dòng đầu tiên của stack trace, hay dòng `Caused by` cuối cùng. Hãy nhìn vào **toàn bộ đồ thị ngoại lệ** cùng các vị trí trong stack trace.

**Ví dụ vấn đề:**

```text
java.lang.IllegalStateException: Cannot import batch
    at ... <frames of service>
    Suppressed: java.lang.IllegalArgumentException: audit cleanup failed
        at ... <frames of cleanup>
Caused by: java.io.IOException: source read failed
    at ... <frames of I/O>
    Suppressed: java.io.IOException: channel close failed
        at ... <frames of close>
```

Đây là **mẫu định dạng minh họa**, không phải output cố định có số dòng thật. Đọc duy nhất dòng `source read failed` sẽ bỏ sót **hai lỗi phụ**: lỗi cleanup của service và lỗi đóng channel trên đối tượng `IOException`. Ngược lại, chỉ nhìn lỗi cleanup cũng không đủ để kết luận nguyên nhân thất bại ban đầu.

## 1. Từ chuỗi nguyên nhân tới cây ngoại lệ

`Throwable` cung cấp hai quan hệ cơ bản giữa các đối tượng lỗi:

- **`getCause()`**: trả về **một** `Throwable` làm nguyên nhân trực tiếp, hoặc `null`. Lần tiếp tục `getCause()` tạo thành *cause chain*.
- **`getSuppressed()`**: trả về mảng `Throwable[]` gồm **không, một hoặc nhiều** lỗi được ghi nhận bổ sung bên cạnh ngoại lệ chính. Mỗi lỗi suppressed cũng có thể có cause hoặc suppressed của riêng nó.

Một mô hình thường gặp:

```text
IllegalStateException: import failed             [ROOT: ngoại lệ bên ngoài]
├── CAUSE ── IOException: read failed
│            └── SUPPRESSED ── IOException: channel close failed
├── SUPPRESSED[0] ── IllegalStateException: rollback failed
└── SUPPRESSED[1] ── IOException: audit log close failed
                           └── CAUSE ── IOException: device full
```

Ở đây, **ROOT** là **ngoại lệ ngoài cùng người gọi đang giữ**, không nhất thiết là “root cause” theo cách nói thông thường. Những nhãn `CAUSE` và `SUPPRESSED` mô tả **các cạnh khác nhau**, không phải mọi nút đều có vai trò ngang nhau.

Hình trên gọi là “cây” để dễ đọc, nhưng nói chính xác hơn, các tham chiếu `Throwable` tạo thành một **đồ thị**: cùng một đối tượng có thể được tham chiếu từ nhiều nơi và các lớp ngoại lệ tùy chỉnh có thể tạo quan hệ vòng. Trình duyệt lỗi tổng quát nên tránh duyệt lặp vô hạn.

### Hai từ “gốc” dễ gây nhầm

| Thuật ngữ | Cách hiểu hữu ích |
| --- | --- |
| **Ngoại lệ ngoài cùng** | Đối tượng đang được ném tới handler/caller hiện tại; ví dụ `IllegalStateException("import failed")` |
| **Nguyên nhân trực tiếp** | Đối tượng mà `outer.getCause()` trả về |
| **Nguyên nhân sâu nhất** | Nút cuối cùng khi lần theo liên tục `getCause()`; chưa chắc là lý do nghiệp vụ duy nhất |
| **Ngoại lệ chính** | Lỗi được ưu tiên giữ khi đồng thời có lỗi trong thao tác chính và lỗi phụ, đặc biệt trong `try-with-resources` |
| **Ngoại lệ suppressed** | Lỗi đính kèm theo quan hệ phụ, không tự trở thành cause |

**Cảnh báo:** đừng lấy “nguyên nhân sâu nhất” rồi tự động bỏ tất cả phần còn lại. Một `IOException` sâu có thể chỉ báo “connection reset”, nhưng tầng ngoài mới biết **tác vụ, đơn hàng hoặc tài nguyên nào** đã bị ảnh hưởng. Suppressed có thể báo thêm sự cố dọn dẹp hoặc tác động chưa hoàn tất.

## 2. Một `Throwable` mang những trường nào?

Đối tượng `java.lang.Throwable` cho phép kiểm tra:

| API | Kết quả | Cần lưu ý |
| --- | --- | --- |
| `getClass().getName()` | Tên lớp ngoại lệ runtime | Khác với tên lớp trong khai báo `catch` |
| `getMessage()` | Thông điệp chi tiết | Có thể `null`; chưa chắc an toàn để công khai |
| `getLocalizedMessage()` | Thông điệp địa phương hóa | Mặc định thường như `getMessage()`; subtype có thể ghi đè |
| `toString()` | Thường là tên lớp cùng message | Không in đầy đủ cây lỗi và frames |
| `getCause()` | Một ngoại lệ nguyên nhân hoặc `null` | Chỉ đi theo nhánh cause |
| `getSuppressed()` | Mảng lỗi phụ, có thể rỗng | Có thể có suppressed ở **bất kỳ nút nào** |
| `getStackTrace()` | Mảng `StackTraceElement[]` | Dấu vết tại thời điểm được ghi, có thể thiếu frame |
| `printStackTrace()` | In biểu diễn nhiều lớp lỗi | Mặc định ra `System.err`, không trả `String` |

Ví dụ:

```java
IllegalStateException top =
        new IllegalStateException(
                "service failed",
                new java.io.IOException("read failed"));

System.out.println(top.getMessage());
System.out.println(top.getCause().getMessage());
System.out.println(top.getSuppressed().length);
```

Đây là một đoạn Java **minh họa**, cần đặt trong lớp/phương thức. Với đối tượng trên:

```text
service failed
read failed
0
```

Đọc riêng `top.getMessage()` chỉ thấy `service failed`. Đọc riêng cause chỉ thấy `read failed`. Không phần nào tự kể đầy đủ diễn biến; cần kết hợp.

## 3. Phân biệt `getMessage()`, `toString()` và `printStackTrace()`

Ba mức biểu diễn hay bị nhầm:

**`getMessage()` — một chuỗi mô tả:** 

```java
System.out.println(ex.getMessage());
```

**`toString()` — tóm tắt loại lỗi kèm message:**

```java
System.out.println(ex);
```

**`printStackTrace()` — trình bày thông tin lỗi, call stack và các quan hệ:**

```java
ex.printStackTrace();
```

Các câu trên là ví dụ nếu `ex` là biến kiểu `Throwable` hợp lệ. Với hành vi mặc định của `Throwable`, `toString()` chứa tên lớp và message nếu có. `printStackTrace()` xuất ra **stderr** và trả `void`; nó có thể in nhiều đoạn `Suppressed:`, `Caused by:` và các frame `at ...`.

Không có phép gọi:

```java
// Cố ý không biên dịch: printStackTrace() trả void.
String trace = ex.printStackTrace();
```

Nếu cần biểu diễn dạng chuỗi, có thể ghi vào `StringWriter`:

```java
java.io.StringWriter buffer = new java.io.StringWriter();
ex.printStackTrace(new java.io.PrintWriter(buffer));
String trace = buffer.toString();
```

Đây là đoạn minh họa, không nên tự chuyển lỗi thành chuỗi ở mọi tầng. Trong ứng dụng thật, một logger hỗ trợ nhận `Throwable` trực tiếp thường thích hợp hơn.

### Bẫy “dòng cuối cùng” trong stack trace

Một bản `printStackTrace` có thể kết thúc bằng `... 5 more`, một frame của cause sâu, hoặc một nhánh suppressed lồng nhau, tùy cấu trúc. **Dòng cuối không phải quy ước đại diện cho nguyên nhân cuối cùng**. Ký hiệu `... N more` chỉ nói rằng các frame trùng đuôi đã được rút gọn khi trình bày.

Muốn hiểu lỗi, đọc **nhãn quan hệ và các đối tượng** chứ không dựa trên vị trí một dòng.

## 4. Cách đọc stack trace theo cấu trúc thay vì từ dưới lên một cách máy móc

Khi bắt gặp một bản trace nhiều tầng, quy trình hữu ích là:

1. **Đọc ngoại lệ ngoài cùng:** loại lỗi, thông điệp, thao tác nào được báo thất bại.
2. **Xem những stack frames liên quan:** chỗ nào tạo/ném ngoại lệ, lớp nào gọi tới nó. Không nhầm frame của wrapper với frame của cause.
3. **Lần theo `Caused by`:** đọc từng nấc bọc lỗi để biết tầng nào chuyển ngữ nghĩa; chú ý cause có thể có message và stack riêng.
4. **Quay lại các nhánh `Suppressed` ở từng nút:** kiểm tra lỗi khi đóng tài nguyên, rollback, flush, dọn dẹp hoặc thao tác phụ.
5. **Đánh giá mức độ ảnh hưởng:** lỗi phụ có thể ảnh hưởng dữ liệu hoặc tài nguyên dù không phải nguyên nhân đầu tiên.
6. **Đối chiếu log có cấu trúc:** request ID, tên tác vụ, trạng thái giao dịch, phiên bản dịch vụ, timestamp, nhưng tránh sao chép dữ liệu nhạy cảm vào báo cáo lỗi.

Đừng chỉ làm bước 3 rồi dừng; mỗi nút cause lại có thể chứa các nhánh suppressed.

### Thứ tự hiển thị không phải thứ tự thời gian tuyệt đối

`Throwable.printStackTrace()` trình bày lỗi theo **cấu trúc liên kết** với indentation và các frame. Nó không phải hệ thống ghi sự kiện theo thời gian. Một lỗi cause được tạo sớm hơn wrapper; lỗi suppressed có thể xảy ra sau thao tác chính; nhưng **vị trí in trong văn bản không đủ để suy ra toàn bộ dòng thời gian** giữa các thread hoặc các hoạt động bất đồng bộ.

Nếu cần phân tích diễn biến chính xác, dùng thêm timestamp/trace ID có cấu trúc tại những ranh giới quan trọng.

## 5. `Caused by` thể hiện việc bọc ngoại lệ như thế nào?

Giả sử tầng đọc dữ liệu ném `IOException`, tầng nghiệp vụ muốn biểu diễn lỗi ở cấp tác vụ:

```java
static void loadProfile() {
    try {
        readProfileFile();
    } catch (java.io.IOException cause) {
        throw new IllegalStateException(
                "profile loading failed",
                cause);
    }
}
```

Đây là **phương thức minh họa**, giả định `readProfileFile()` tồn tại và ném `IOException`.

Tại tầng ngoài, đối tượng đang được ném là `IllegalStateException`, có stack trace tại nơi tạo wrapper. `getCause()` dẫn tới `IOException` gốc với stack trace riêng. Khi in đầy đủ, Java sẽ biểu diễn liên kết này dưới nhãn `Caused by:`.

**Phân biệt:**

- `throw original;`: ném lại **cùng đối tượng**, thường giữ stack trace đã được ghi.
- `throw new X("context", original);`: tạo ngoại lệ **mới** có cause là `original`.
- `throw new X("context");`: tạo ngoại lệ mới mà **không tự bảo toàn cause**.

Caller bắt theo **kiểu runtime của đối tượng ngoài cùng**, không tự động bắt một cause bên trong theo kiểu của cause đó. Chẳng hạn `catch (IOException)` không bắt một `IllegalStateException` chỉ vì cause là `IOException`.

### Root cause có luôn là nút cuối của `getCause()`?

“Nút sâu nhất trong cause chain” là định nghĩa kỹ thuật của một điểm cuối trên nhánh cause. Nhưng về vận hành, đó **không luôn là câu trả lời hoàn chỉnh**:

- `TimeoutException` sâu nhất cho biết timeout; service ngoài cho biết **thao tác nào** bị timeout.
- `NumberFormatException` sâu nhất cho biết không parse được số; tầng nghiệp vụ cho biết **trường dữ liệu nào** sai.
- Một thư viện có thể bọc sai hoặc che mất cause.
- Nhánh suppressed có thể hé lộ lỗi đóng/rollback thứ hai cần xử lý độc lập.
- Cùng một lỗi kỹ thuật có thể dẫn đến nhiều hậu quả nghiệp vụ khác nhau.

Vì vậy, hãy đọc cause chain để hiểu **nguồn phát sinh**, còn wrapper và suppressed giúp hiểu **ngữ cảnh và hậu quả bổ sung**.

## 6. `Suppressed` là nhánh phụ, không phải một cause thứ hai

Một ngoại lệ có thể mang nhiều suppressed exceptions:

```java
IllegalStateException primary =
        new IllegalStateException("main operation failed");

primary.addSuppressed(
        new java.io.IOException("close reader failed"));
primary.addSuppressed(
        new java.io.IOException("close audit stream failed"));
```

Đoạn trên là **mã minh họa**. Ở đây:

- `primary.getCause()` là `null`.
- `primary.getSuppressed().length` là `2`.
- Mỗi suppressed exception có thể lại có `getCause()` hoặc `getSuppressed()` riêng.

`getSuppressed()` không phải `getCause()`. Một lỗi đóng reader **không nhất thiết là nguyên nhân** làm thao tác chính thất bại; nó phát sinh trong quá trình dọn dẹp và được giữ lại thay vì che khuất lỗi chính.

### Vì sao suppressed có thể nằm trên một cause, không phải ở ngoại lệ ngoài?

Giả sử tầng thấp dùng `try-with-resources` và ném `IOException("read failed")`. Khi `close()` ném lỗi, Java gắn lỗi đóng vào **đối tượng IOException đó**. Sau đó tầng service bọc IOException trong `IllegalStateException("service failed", cause)`.

Sơ đồ:

```text
IllegalStateException("service failed")
└── CAUSE → IOException("read failed")
             └── SUPPRESSED → IOException("close failed")
```

Lúc này:

```java
outer.getSuppressed().length
```

có thể là `0`, nhưng:

```java
outer.getCause().getSuppressed().length
```

lại là `1`. Đây là lý do **chỉ gọi `getSuppressed()` trên wrapper ngoài cùng có thể bỏ sót lỗi**.

Hai câu trên là biểu thức minh họa, giả định `outer` tham chiếu đúng ngoại lệ và cause không null.

### Lỗi phụ vẫn cần quan tâm

Không phải suppressed luôn “không quan trọng”. Ví dụ:

- Lỗi đóng output stream có thể báo dữ liệu chưa được ghi hết.
- Lỗi rollback hoặc dọn dẹp có thể để tài nguyên ở trạng thái không xác định.
- Lỗi đóng audit channel có thể khiến một số dữ liệu kiểm toán không được ghi nhận.
- Nhiều lần đóng resource cùng thất bại có thể báo sự cố cơ sở hạ tầng rộng hơn lỗi chính.

**Vai trò suppressed là giữ thông tin theo đúng ngữ nghĩa**, không phải quyết định tự động bỏ qua vấn đề.

## 7. Ví dụ Java 17+ hoàn chỉnh: dựng và duyệt cây ngoại lệ

Để hiển thị cấu trúc ổn định mà không lệ thuộc số dòng stack trace, chương trình sau tạo một đồ thị ngoại lệ với cause và suppressed ở nhiều tầng. Nó dùng `IdentityHashMap` để nhận diện **cùng một đối tượng Throwable**, tránh lặp vô hạn nếu đồ thị chứa tham chiếu vòng hoặc dùng chung một đối tượng.

Lưu tệp **`ThrowableTreeDemo.java`**:

```java
import java.io.IOException;
import java.io.PrintWriter;
import java.io.StringWriter;
import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.Set;

public class ThrowableTreeDemo {

    static Throwable buildFailure() {
        IOException read =
                new IOException("storage read failed");

        read.addSuppressed(
                new IOException("channel close failed"));

        IllegalStateException service =
                new IllegalStateException(
                        "load profile failed", read);

        service.addSuppressed(
                new IllegalArgumentException(
                        "unlock cleanup failed"));

        IllegalStateException audit =
                new IllegalStateException("audit close failed");

        audit.addSuppressed(
                new IOException("audit stream close failed"));

        service.addSuppressed(audit);
        return service;
    }

    static void printTree(
            Throwable error,
            String indent,
            String relation,
            Set<Throwable> visited) {

        if (error == null) {
            return;
        }

        System.out.println(
                indent + relation
                + error.getClass().getSimpleName()
                + ": " + String.valueOf(error.getMessage()));

        if (!visited.add(error)) {
            System.out.println(indent + "  [already visited]");
            return;
        }

        Throwable cause = error.getCause();
        if (cause != null) {
            printTree(cause, indent + "  ", "CAUSE -> ", visited);
        }

        Throwable[] suppressed = error.getSuppressed();
        for (int i = 0; i < suppressed.length; i++) {
            printTree(
                    suppressed[i],
                    indent + "  ",
                    "SUPPRESSED[" + i + "] -> ",
                    visited);
        }
    }

    public static void main(String[] args) {
        Throwable error = buildFailure();

        Set<Throwable> visited =
                Collections.newSetFromMap(
                        new IdentityHashMap<Throwable, Boolean>());

        printTree(error, "", "ROOT -> ", visited);

        StringWriter buffer = new StringWriter();
        error.printStackTrace(new PrintWriter(buffer));
        String trace = buffer.toString();

        System.out.println(
                "TRACE_HAS_CAUSE="
                + trace.contains(
                        "Caused by: java.io.IOException: storage read failed"));

        System.out.println(
                "TRACE_HAS_SUPPRESSED="
                + trace.contains(
                        "Suppressed: java.lang.IllegalArgumentException: "
                        + "unlock cleanup failed"));

        System.out.println(
                "CAUSE_SUPPRESSED_COUNT="
                + error.getCause().getSuppressed().length);
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 ThrowableTreeDemo.java
java ThrowableTreeDemo
```

**Stdout dự kiến chính xác:**

```text
ROOT -> IllegalStateException: load profile failed
  CAUSE -> IOException: storage read failed
    SUPPRESSED[0] -> IOException: channel close failed
  SUPPRESSED[0] -> IllegalArgumentException: unlock cleanup failed
  SUPPRESSED[1] -> IllegalStateException: audit close failed
    SUPPRESSED[0] -> IOException: audit stream close failed
TRACE_HAS_CAUSE=true
TRACE_HAS_SUPPRESSED=true
CAUSE_SUPPRESSED_COUNT=1
```

### Vì sao ví dụ này thực sự duyệt “cây” thay vì chỉ đi theo một nhánh?

- `printTree` nhận một **nút `Throwable`**.
- Nếu có `getCause()`, chương trình đi vào **nhánh nguyên nhân**.
- Sau đó nó duyệt **toàn bộ mảng `getSuppressed()`** của **chính nút đang xét**.
- Mỗi cause hoặc suppressed lại được duyệt bằng cùng một hàm, nên các ngoại lệ phụ ở cấp sâu **không bị bỏ sót**.
- `visited` dùng đồng nhất tham chiếu (*reference identity*), không dùng `equals()` hay so sánh message. Hai lỗi khác nhau có thể có cùng kiểu và cùng thông điệp; chúng vẫn là hai đối tượng cần ghi nhận.
- Việc in `[already visited]` nếu gặp lại cùng đối tượng giúp tránh duyệt vòng/lặp vô hạn trong các cấu trúc bất thường.

Chương trình cũng lấy raw `printStackTrace` vào `StringWriter` rồi **chỉ kiểm tra dấu hiệu ổn định** như `Caused by` và `Suppressed`. Số dòng tệp, package hay frame cụ thể có thể thay đổi nên không hard-code toàn bộ bản stack trace vào stdout.

### Thứ tự duyệt do ứng dụng lựa chọn

Ví dụ in **cause trước, suppressed sau** để ưu tiên phân tích nguyên nhân chính. Đây là **quy ước trình bày do ví dụ chọn**, không phải cam kết rằng `Throwable.printStackTrace()` in theo cùng thứ tự. Hãy luôn phân biệt **đồ thị dữ liệu** với **cách trình bày văn bản** của từng công cụ.

Trong hệ thống thực, một bộ duyệt tổng quát còn nên giới hạn độ sâu, số nút và dung lượng message, để một đồ thị lỗi lớn hoặc dữ liệu không đáng tin không làm log quá tải.

## 8. Ví dụ Java 17+ hoàn chỉnh: lỗi đọc, lỗi đóng và wrapper ở tầng trên

Một tình huống tự nhiên tạo nhánh suppressed là `try-with-resources`. Khi phần thân ném lỗi đọc và `close()` cũng thất bại, Java bảo toàn lỗi đọc làm ngoại lệ chính và giữ lỗi đóng trong `getSuppressed()`.

Lưu tệp **`ResourceCauseTreeDemo.java`**:

```java
import java.io.IOException;

public class ResourceCauseTreeDemo {

    static final class TrackedResource implements AutoCloseable {
        private final String name;

        TrackedResource(String name) {
            this.name = name;
            System.out.println("open " + name);
        }

        @Override
        public void close() {
            System.out.println("close " + name);
            throw new IllegalStateException(
                    "close failed: " + name);
        }
    }

    static void readBatch() throws IOException {
        try (TrackedResource first = new TrackedResource("A");
             TrackedResource second = new TrackedResource("B")) {

            System.out.println("work: reading");
            throw new IOException("source read failed");
        }
    }

    static void importBatch() {
        try {
            readBatch();
        } catch (IOException cause) {
            throw new IllegalStateException(
                    "batch import failed", cause);
        }
    }

    public static void main(String[] args) {
        try {
            importBatch();
        } catch (IllegalStateException outer) {
            System.out.println("OUTER: " + outer.getMessage());
            System.out.println(
                    "OUTER_SUPPRESSED="
                    + outer.getSuppressed().length);

            Throwable cause = outer.getCause();

            System.out.println(
                    "CAUSE: " + cause.getClass().getSimpleName()
                    + ": " + cause.getMessage());

            System.out.println(
                    "CAUSE_SUPPRESSED="
                    + cause.getSuppressed().length);

            for (Throwable secondary : cause.getSuppressed()) {
                System.out.println(
                        "SECONDARY: " + secondary.getMessage());
            }
        }
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 ResourceCauseTreeDemo.java
java ResourceCauseTreeDemo
```

**Stdout dự kiến chính xác:**

```text
open A
open B
work: reading
close B
close A
OUTER: batch import failed
OUTER_SUPPRESSED=0
CAUSE: IOException: source read failed
CAUSE_SUPPRESSED=2
SECONDARY: close failed: B
SECONDARY: close failed: A
```

### Diễn biến chính xác

1. `TrackedResource A` và `B` được tạo; mỗi constructor in tên tương ứng.
2. Phần thân `try` ném `IOException("source read failed")`.
3. Java gọi `close()` theo **thứ tự ngược khai báo**: B trước, A sau.
4. Cả hai `close()` ném `IllegalStateException`. Vì thân `try` đã có ngoại lệ chính, lỗi đóng được **gắn suppressed trên chính đối tượng `IOException`**.
5. Tầng `importBatch` bắt `IOException` đó và bọc thành `IllegalStateException("batch import failed", cause)`.
6. Handler ở `main` nhận wrapper. `outer.getSuppressed()` rỗng, nhưng `outer.getCause().getSuppressed()` có **hai** lỗi đóng B và A.
7. Nếu người điều tra chỉ đọc message của wrapper hoặc chỉ xem suppressed của wrapper, họ sẽ **không phát hiện đầy đủ hai lỗi cleanup**.

Đây chính là lý do đề bài yêu cầu **đọc cây ngoại lệ**, không chỉ đọc thông điệp cuối.

### Không đánh đồng lỗi đóng với lỗi chính

Trong ví dụ này, lỗi đọc nguồn là nguyên nhân khiến xử lý batch dừng lại. Lỗi đóng B và A xảy ra trong lúc dọn dẹp. Chúng không làm cho ngoại lệ chính biến thành `IllegalStateException` tại tầng đọc, nhưng vẫn quan trọng: trong ứng dụng thật, lỗi đóng có thể ảnh hưởng việc flush, hủy kết nối hoặc trạng thái resource.

## 9. Cách hiển thị của `printStackTrace` có thể khác cây tự dựng

`Throwable.printStackTrace()` thường in ngoại lệ ngoài cùng, các frame, rồi nội dung suppressed và cause theo cách định dạng của Java. Ví dụ đoạn:

```text
java.lang.IllegalStateException: batch import failed
    at example.ImportService.importBatch(ImportService.java:<line>)
Caused by: java.io.IOException: source read failed
    at example.Reader.readBatch(Reader.java:<line>)
    Suppressed: java.lang.IllegalStateException: close failed: B
        at example.Resource.close(Resource.java:<line>)
    Suppressed: java.lang.IllegalStateException: close failed: A
        at example.Resource.close(Resource.java:<line>)
```

Đây chỉ là **hình dạng minh họa**. Java có thể thêm/rút gọn nhiều dòng `at ...` và `... N more`. Ý nghĩa không đổi: suppressed B/A được **gắn với cause `IOException`**, không phải wrapper `IllegalStateException` bên ngoài.

Dấu thụt đầu dòng rất hữu ích: nó cho thấy nhánh lỗi thuộc ngoại lệ nào. Nếu log collector làm phẳng hoặc cắt mất thụt đầu dòng, bản văn có thể trở nên khó hiểu; khi đó cần giữ dữ liệu có cấu trúc hoặc stack trace nguyên vẹn.

### `... N more` nghĩa là gì?

Khi cause và wrapper chia sẻ phần cuối của call stack, `printStackTrace()` có thể ghi:

```text
... 4 more
```

Nghĩa là bốn frame cuối trùng với những frame đã được in ở phần bao ngoài, nên được rút gọn. Nó **không có nghĩa đã mất bốn tầng cause** hoặc Java chỉ giữ bốn frame. `getStackTrace()` vẫn là API có cấu trúc để xem các frame thuộc từng đối tượng lỗi.

**Không dùng văn bản `printStackTrace` làm giao thức máy móc ổn định.** Tên module, class loader, số dòng, số frame và cách trình bày có thể thay đổi khi build/runtime thay đổi. Khi cần xử lý chương trình, hãy đọc `getCause()` và `getSuppressed()` trực tiếp.

## 10. Tại sao chỉ lấy “root cause” vẫn chưa đủ?

Một hàm tiện ích đơn giản thường làm:

```java
static Throwable deepestCause(Throwable error) {
    Throwable current = error;
    while (current.getCause() != null) {
        current = current.getCause();
    }
    return current;
}
```

Đây là **hàm minh họa**; nó hợp lý với một cause chain hữu hạn, không có vòng. Tuy nhiên:

- Nó **chỉ đi theo `getCause()`**, không đọc nhánh suppressed của bất kỳ nút nào.
- Nó **bỏ thông điệp nghiệp vụ của wrapper**, khiến người điều tra khó biết thao tác nào thất bại.
- Nó không trả toàn bộ stack trace, chỉ trả một đối tượng cuối chuỗi.
- Với các đồ thị bất thường có vòng tham chiếu, vòng lặp `while` không có bảo vệ có thể không kết thúc.
- “Nguyên nhân cuối cùng” chưa chắc là thứ duy nhất quan trọng với dữ liệu đã ghi dở, cleanup thất bại hoặc giao dịch không hoàn tất.

Nếu chỉ cần quyết định một nhánh retry theo lỗi mạng cụ thể, kiểm tra cause chain có thể hữu ích. Nhưng nếu mục tiêu là **báo cáo đầy đủ sự cố**, hãy duyệt cause **và** suppressed cùng với các stack traces liên quan.

### Đừng dựa vào chuỗi message để phân loại

Không nên viết:

```java
if (ex.getMessage().contains("connection")) {
    // Quyết định thử lại.
}
```

Vấn đề: `getMessage()` có thể `null`, thông điệp thay đổi theo phiên bản/thư viện/ngôn ngữ, và từ `connection` có thể xuất hiện trong nhiều lỗi bản chất khác nhau. Khi chương trình cần phân loại để hành động, ưu tiên **kiểu ngoại lệ**, mã lỗi có cấu trúc hoặc trạng thái chính thức do API cung cấp.

Bộ duyệt cây là công cụ **chẩn đoán**, không phải lời khuyên coi mọi suppressed/cause đều có cùng chính sách retry.

## 11. Thuật toán duyệt an toàn: identity, giới hạn và không phá dữ liệu gốc

Ví dụ `ThrowableTreeDemo` đã dùng:

```java
Set<Throwable> visited =
        java.util.Collections.newSetFromMap(
                new java.util.IdentityHashMap<Throwable, Boolean>());
```

Đây là đoạn minh họa. Tại sao không chỉ dùng `HashSet`?

- Mục tiêu của `visited` là hỏi **đã gặp đúng đối tượng lỗi này chưa**, không hỏi hai lỗi có cùng thông điệp hoặc `equals()` hay không.
- Một lớp `Throwable` tùy chỉnh có thể ghi đè `equals()`/`hashCode()`.
- So sánh **reference identity** tránh gộp nhầm hai đối tượng lỗi khác nhau.
- Quan hệ có thể chia sẻ một cùng đối tượng ở nhiều nhánh; in nhãn *already visited* giữ cấu trúc đủ hiểu mà không đệ quy vô hạn.

Trong hệ thống cho phép tiếp nhận lỗi từ plugin hay extension, cần bổ sung:

1. **Giới hạn độ sâu**: tránh stack overflow của chính bộ duyệt nếu đồ thị cực sâu.
2. **Giới hạn số nút**: tránh tốn CPU/bộ nhớ trên lỗi có quá nhiều suppressed.
3. **Giới hạn số ký tự message/stack**: một exception có thể chứa dữ liệu đầu vào dài bất thường.
4. **Xử lý lỗi khi formatter chạy**: một lớp tùy chỉnh có thể ghi đè các phương thức biểu diễn, nên không nên giả định mọi quá trình định dạng đều vô hại.
5. **Không sửa đối tượng gốc khi đọc**: tránh `setStackTrace`, `initCause` hay `addSuppressed` chỉ để “đẹp log”.
6. **Bảo vệ dữ liệu nhạy cảm**: không in raw message ra các kênh công khai.

Những giới hạn này dành cho công cụ điều tra tổng quát; ví dụ giáo dục cố ý nhỏ để thấy rõ các nhánh.

### Không phải mọi đồ thị đều thuần “cây”

`Throwable.addSuppressed()` cấm trực tiếp tự suppress chính mình, nhưng các tham chiếu qua cause hoặc suppressed ở nhiều đối tượng có thể làm cấu trúc phức tạp. Java `printStackTrace` cũng có biện pháp đánh dấu tham chiếu vòng khi trình bày. Vì vậy tư duy **duyệt đồ thị có phát hiện lặp** là an toàn hơn giả định mọi Throwable chỉ xuất hiện ở một nhánh.

## 12. Log đầy đủ nhưng không log trùng và không lộ bí mật

Một lỗi có thể đi qua repository → service → controller → task boundary. Nếu tầng nào cũng gọi `printStackTrace()` rồi `throw ex;`, một sự cố có thể tạo nhiều bản trace trùng hoặc gần trùng. Điều này không làm cây ngoại lệ “đầy đủ hơn”; nó khiến log nhiễu và tốn tài nguyên.

Gợi ý phân chia:

- **Tầng thấp** ném đúng loại lỗi, cung cấp cause khi cần, quản lý tài nguyên và giữ suppressed của lỗi chính.
- **Tầng nghiệp vụ** chỉ bọc khi bổ sung ngữ cảnh thật hoặc thay đổi hợp đồng lỗi.
- **Ranh giới xử lý** quyết định phục hồi, trả kết quả thất bại, hoặc ghi log tập trung.
- **Logger** nhận đối tượng `Throwable` để formatter có thể trình bày cause và suppressed.

Ví dụ với Java Util Logging:

```java
java.util.logging.Logger logger =
        java.util.logging.Logger.getLogger("batch.import");

logger.log(
        java.util.logging.Level.SEVERE,
        "Batch import failed",
        ex);
```

Đây là **đoạn minh họa**, `ex` cần là `Throwable` đã được bắt ở ranh giới phù hợp. Truyền nguyên đối tượng giúp logger giữ thông tin nhiều lớp. Chỉ viết `logger.severe(ex.getMessage())` thì thiếu thông tin cause/stack/suppressed.

### Tránh lộ dữ liệu nhạy cảm từ bất kỳ nút nào

Không chỉ message của ngoại lệ ngoài cùng có thể chứa dữ liệu nhạy cảm. Cause hoặc suppressed do một thư viện tạo ra có thể mang:

- Đường dẫn tệp và cấu hình nội bộ.
- Chuỗi kết nối hoặc thông tin đăng nhập nếu code xử lý thiếu an toàn.
- Định danh người dùng, nội dung yêu cầu, payload dữ liệu.
- Chi tiết triển khai dịch vụ, bảng database, câu SQL.

Do đó:

- Không trả cây stack trace nguyên văn cho API client hoặc người dùng cuối.
- Không đính kèm mật khẩu, token, cookie, mã xác thực vào message lúc tạo ngoại lệ.
- Kiểm soát truy cập, thời gian lưu và mức độ chi tiết của log nội bộ.
- Dùng request ID/correlation ID **không nhạy cảm** cho việc nối log, thay vì chép nguyên payload.
- Khi báo lỗi công khai, đưa ra mã lỗi ổn định và thông báo thích hợp; giữ chi tiết kỹ thuật tại hệ thống quan sát có quyền truy cập đúng.

Một cây lỗi “đầy đủ” về mặt kỹ thuật không có nghĩa được phép công khai mọi chi tiết của nó.

## 13. Khi nào nên xử lý từng nhánh, khi nào chỉ quan sát?

Đọc được nhiều nhánh **không đồng nghĩa** rằng tất cả phải được bắt và xử lý riêng ở cùng một tầng.

Ví dụ:

| Tình huống | Điều có thể cần làm |
| --- | --- |
| Cause là lỗi nhập liệu đã được phân loại | Trả lỗi validation thích hợp, không retry vô hạn |
| Cause là lỗi mạng tạm thời theo hợp đồng API | Cân nhắc retry có giới hạn và idempotency |
| Suppressed là lỗi đóng stream sau khi đọc thất bại | Lưu dấu chẩn đoán về cleanup, kiểm tra trạng thái tài nguyên |
| Suppressed là lỗi rollback | Báo vận hành vì trạng thái giao dịch có thể cần điều tra |
| Cause sâu nhất là lỗi thư viện nhưng wrapper có mã nghiệp vụ | Giữ cả hai: phân loại theo hợp đồng tầng phù hợp, điều tra kỹ thuật qua cause |
| Không có cause/suppressed | Đọc kiểu ngoại lệ, message, stack và ngữ cảnh công việc hiện có |

Không tự động retry chỉ vì thấy một `IOException` ở đâu đó trong cây. Nó có thể là suppressed của thao tác đóng sau một lỗi chính khác, hoặc đã được wrapper biểu diễn thành lỗi không thể phục hồi. Chính sách xử lý phải xét **vai trò của nhánh** và hợp đồng của tầng đang ra quyết định.

## 14. Những hiểu lầm và lỗi thường gặp

| Ngộ nhận/lỗi | Vì sao không đúng | Cách tốt hơn |
| --- | --- | --- |
| “Thông điệp cuối cùng là toàn bộ lỗi” | Bỏ wrapper, cause, suppressed và stack | Đọc đối tượng lỗi cùng quan hệ |
| “Lấy sâu nhất trong `getCause()` là đủ” | Không duyệt suppressed, mất ngữ cảnh | Duyệt cả cause và suppressed |
| “Suppressed là một cause khác” | Đây là hai quan hệ ngữ nghĩa khác nhau | Phân biệt `getCause()` và `getSuppressed()` |
| “Suppressed chỉ nằm ở root” | Mỗi nút `Throwable` có thể mang suppressed riêng | Xem suppressed ở **mọi nút** |
| “`printStackTrace` in một chuỗi ổn định” | Số dòng/khung/định dạng thay đổi | Kiểm thử kiểu, cause, suppressed; không so raw trace |
| “`... N more` nghĩa là mất dữ liệu” | Chỉ rút gọn khung trùng trong bản in | Đọc `getStackTrace()` nếu cần |
| “Chỉ lấy `ex.getMessage()` khi log lỗi” | Mất dữ liệu chẩn đoán | Truyền `Throwable` trực tiếp cho logger |
| “Ném wrapper mới thì cause tự giữ” | Không nếu constructor không nhận cause | Dùng `new X(message, original)` khi thích hợp |
| “Suppressed không quan trọng” | Có thể báo lỗi ghi/rollback/close | Kiểm tra ảnh hưởng vận hành |
| “Hai lỗi có cùng message là một” | Có thể là hai đối tượng khác nhau | Dùng reference identity khi cần duyệt |
| “Cứ bắt `Throwable` rồi nuốt lỗi” | Có thể giấu `Error` và trạng thái không thể phục hồi | Đặt chính sách xử lý ở tầng phù hợp |
| “Có trace là biết chính xác dòng thời gian” | Stack không phải event log nhiều thread | Dùng timestamp, correlation/tracing có cấu trúc |
| “Có thể gửi nguyên trace cho client” | Có nguy cơ lộ thông tin | Phân tách phản hồi công khai và log nội bộ |

## 15. Bài tập kiểm tra cách đọc cây ngoại lệ

**Bài A — tìm nút có suppressed**

```text
ServiceException("job failed")
└── CAUSE → IOException("read failed")
             └── SUPPRESSED → IOException("close failed")
```

**Hỏi:** `serviceError.getSuppressed().length` có thể bằng bao nhiêu, và cần đọc ở đâu để thấy lỗi đóng?

**Đáp án:** có thể bằng `0`. Lỗi đóng nằm trên **cause**; đọc `serviceError.getCause().getSuppressed()` sau khi kiểm tra cause không null.

**Bài B — handler bắt gì?**

`IllegalStateException` ngoài cùng có cause `IOException`. Handler chỉ viết `catch (IOException ex)` có tự bắt wrapper không?

**Không.** Handler xét loại runtime của đối tượng đang được ném, không tự đi qua cause. Muốn xử lý wrapper phải bắt kiểu phù hợp hoặc điều chỉnh thiết kế API.

**Bài C — hai suppressed exceptions**

Thân `try-with-resources` ném `IOException("body")`, B.close rồi A.close ném lỗi. Lỗi nào thường là chính?

**`IOException("body")`**; hai lỗi đóng được gắn suppressed trên ngoại lệ chính, theo thứ tự đóng B trước A.

**Bài D — dòng `... 3 more`**

Nó có nghĩa ba ngoại lệ bị mất không?

**Không.** Đó thường là ba **khung stack trùng phần cuối** đã được rút gọn khi in một nhánh cause/suppressed.

**Bài E — cùng một exception xuất hiện hai lần**

Bộ duyệt thấy một đối tượng `Throwable` được tham chiếu lại ở nhánh khác. Có nên tiếp tục đệ quy vô điều kiện không?

**Không.** Dùng tập đối tượng đã thăm theo reference identity và ghi nhận việc đã gặp để tránh lặp/cycles.

**Bài F — lỗi nào đáng quan tâm hơn?**

Một lỗi đọc là primary; rollback thất bại nằm trong suppressed. Có được bỏ qua rollback vì chỉ là “phụ” không?

**Không nên tự động bỏ qua.** Lỗi rollback có thể ảnh hưởng tính nhất quán; cách xử lý dựa vào hợp đồng giao dịch và mức độ tác động của hệ thống.

**Bài G — chỉ đọc log message**

Log chỉ còn dòng `"batch failed"` và không lưu `Throwable`. Có thể tái tạo chắc chắn source line, cause và suppressed chỉ từ message này không?

**Không.** Thông tin đã không được ghi nhận trong dòng log; không thể suy ra đáng tin. Cần giữ đối tượng lỗi hoặc bản trace/cấu trúc tương ứng tại ranh giới logging.

**Bài H — cây hay chuỗi?**

Nếu một cause có ba suppressed và một suppressed lại có cause, tại sao chỉ lặp `while (ex.getCause() != null)` là chưa đủ?

Vì vòng lặp này chỉ đi theo **một loại cạnh `cause`**, bỏ tất cả cạnh suppressed và nguyên nhân nằm sâu trong các nhánh phụ.

## 16. Checklist điều tra lỗi thực tế

Khi cần hiểu một exception Java nhiều tầng:

1. **Giữ đối tượng `Throwable` ngoài cùng** hoặc bản stack trace đầy đủ được ghi đúng ranh giới.
2. **Xác định loại và thông điệp ngoài** để biết tác vụ/hợp đồng nào thất bại.
3. **Lần theo `getCause()`** từng tầng, không dừng ở message đầu hoặc dòng cuối.
4. **Tại mỗi tầng, đọc `getSuppressed()`**, rồi tiếp tục duyệt các nhánh con.
5. **Giữ phân biệt cause/suppressed** trong báo cáo: nguyên nhân khác với lỗi cleanup.
6. **Quan sát stack trace của từng nút** khi cần vị trí code; nhớ nơi ghi stack không nhất thiết là nơi rethrow.
7. **Hiểu `... N more`** là rút gọn khung trùng chứ không phải một lỗi mới.
8. **Tránh suy diễn từ văn bản log** khi đã có API dữ liệu `Throwable`; không parse message để quyết định nghiệp vụ.
9. **Dùng identity và giới hạn duyệt** nếu viết công cụ duyệt tổng quát.
10. **Đánh giá cả lỗi chính và lỗi phụ** về ảnh hưởng dữ liệu/tài nguyên, không coi suppressed là vô hại.
11. **Ghi log một cách tập trung** và giữ cause đúng khi chuyển lỗi; không lặp lại toàn bộ trace ở mọi tầng.
12. **Kiểm soát dữ liệu nhạy cảm** trong mọi message, cause, suppressed và stack trace trước khi lưu/chia sẻ.

## Kết luận

**Một ngoại lệ Java không chỉ là một thông điệp.** Đối tượng `Throwable` có **kiểu lỗi, message, stack trace, một cause trực tiếp và danh sách suppressed**. Vì mỗi cause hoặc suppressed lại có thể dẫn tới các đối tượng lỗi khác, ta cần suy nghĩ theo **cấu trúc phân nhánh** thay vì chỉ đọc một dòng `Caused by` cuối cùng.

Cách điều tra đáng tin cậy là đọc **ngữ cảnh của wrapper**, **nguyên nhân trên chuỗi `getCause()`**, **các nhánh `getSuppressed()` ở mọi nút**, rồi đối chiếu stack frames và log vận hành. Điều này giữ được cả **thất bại chính** lẫn **lỗi cleanup/rollback liên quan**, giúp chẩn đoán đúng mà không phụ thuộc vào câu chữ hay số dòng của một bản stack trace.