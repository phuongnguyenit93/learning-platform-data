# Quản lý Process, FileChannel và tài nguyên JDBC

Một tác vụ tích hợp thường phải gọi chương trình bên ngoài, lưu kết quả ra file và ghi trạng thái vào database. Ba phần này có vòng đời và cơ chế lỗi khác nhau: tiến trình hệ điều hành có thể timeout, file có thể ghi dở hoặc lỗi lưu trữ, còn transaction JDBC có thể rollback hoặc mất kết nối đúng lúc commit.

Bài thực hành xây dựng một pipeline xuất dữ liệu: **khởi chạy producer bằng ProcessBuilder, nhận file kết quả, sao chép và kiểm tra dữ liệu bằng FileChannel, sau đó ghi metadata vào database bằng transaction JDBC**. Pipeline quản lý rõ trạng thái `PROCESSING`, `READY`, `FAILED`; dùng timeout, giới hạn dung lượng, checksum, atomic move và quy trình phục hồi khi ứng dụng dừng giữa chừng.

Các API cốt lõi đều ổn định trên JDK 26:

- `ProcessBuilder` và `Process` dùng để tạo và quản lý tiến trình ngoài. JDK 26 bổ sung `Process.close()` qua `AutoCloseable`.
- `FileChannel` cung cấp đọc/ghi theo vị trí, sao chép dữ liệu và `force()`.
- JDBC `Connection`, `PreparedStatement` và transaction quản lý thay đổi database.
- JDBC 4.5 MR5 là API chuẩn trong JDK 26; tính năng JSON/DECFLOAT hoặc SQL dialect cụ thể vẫn phụ thuộc driver và database.

Không có transaction JDBC tiêu chuẩn nào tự động bao trùm một lần đổi tên file trên filesystem. Vì vậy, bài thực hành thiết kế trạng thái và recovery để xử lý khoảng thời gian giữa thao tác file và commit database.

## 1. Kịch bản và hợp đồng của pipeline

Một hệ thống cần chạy công cụ xuất dữ liệu theo yêu cầu người dùng. Công cụ producer ghi dữ liệu nhị phân ra stdout và ghi thông tin chẩn đoán ra stderr. Ứng dụng Java cần:

1. Tạo mã job duy nhất và ghi nhận job bắt đầu trong database.
2. Khởi chạy producer bằng danh sách executable/arguments đã được cấu hình tin cậy.
3. Chuyển stdout và stderr sang file staging, không để pipe đầy làm treo process.
4. Áp dụng thời hạn chạy và giới hạn kích thước output.
5. Chỉ chấp nhận exit code thành công.
6. Đọc file staging qua FileChannel, tính SHA-256, ghi sang file tạm và gọi `force(true)`.
7. Đổi tên file tạm thành artifact hoàn chỉnh bằng atomic move trên cùng filesystem.
8. Mở transaction JDBC, chuyển job từ `PROCESSING` sang `READY` và lưu đường dẫn, kích thước, checksum.
9. Khi có lỗi, ghi trạng thái `FAILED` nếu file chưa được publish; nếu file đã publish nhưng commit chưa xác định, để job ở `PROCESSING` để tiến trình reconciliation xử lý.

Mô hình trạng thái:

    NEW
     |
     | insert job row and commit
     v
    PROCESSING
     |
     | producer exits 0
     | copy + hash + force
     | atomic move
     v
    FILE_PUBLISHED
     |
     | JDBC update + commit
     v
    READY

    PROCESSING -- process/I/O failure before publish --> FAILED

`FILE_PUBLISHED` là trạng thái trung gian trong luồng điều khiển ứng dụng; ví dụ schema bên dưới vẫn lưu row ở `PROCESSING` cho đến khi database xác nhận `READY`. Nhờ vậy, nếu JVM dừng sau atomic move nhưng trước commit, worker phục hồi có thể nhận diện job chưa hoàn tất.

### Hợp đồng đầu vào/đầu ra

| Thuộc tính | Quy tắc |
|---|---|
| Job ID | UUID được tạo một lần cho một yêu cầu logic; retry phải tra cứu cùng ID |
| Command | Danh sách executable và argument từ cấu hình allowlist; không nhận nguyên chuỗi shell từ request |
| Working directory | Thư mục được ứng dụng kiểm soát |
| stdout | File staging riêng của job |
| stderr | File log riêng, giới hạn dung lượng và quyền đọc |
| Timeout | Dùng monotonic clock để đo thời lượng |
| Output limit | Giới hạn dữ liệu và log; ngưỡng kiểm tra định kỳ là best-effort |
| Artifact | File hoàn chỉnh chỉ xuất hiện sau khi copy, hash, force và atomic move thành công |
| Database state | Chỉ chuyển sang `READY` sau khi artifact đã được publish |
| Retry | Không chạy lại producer mù quáng nếu job cũ có thể đã tạo side effect |

Các đoạn mã dưới đây là những phần của cùng một lớp `ExportPipeline`; cần ghép các method và record vào lớp đó, rồi bổ sung cấu hình `DataSource`, command và schema theo môi trường. Các import chính:

    import java.io.IOException;
    import java.nio.ByteBuffer;
    import java.nio.channels.ClosedByInterruptException;
    import java.nio.channels.FileChannel;
    import java.nio.file.*;
    import java.security.MessageDigest;
    import java.security.NoSuchAlgorithmException;
    import java.sql.*;
    import java.time.Duration;
    import java.util.HexFormat;
    import java.util.List;
    import java.util.UUID;
    import java.util.concurrent.TimeUnit;
    import java.util.concurrent.TimeoutException;
    import javax.sql.DataSource;

Trong ứng dụng modular, khai báo `requires java.sql;`. Biên dịch mã sau khi ghép thành lớp hoàn chỉnh bằng JDK 26 và JDBC driver tương thích, ví dụ `javac --release 26 -cp "lib/database-driver.jar" -d out src/ExportPipeline.java`. Không cần bật preview cho các API trong bài.

## 2. Tạo schema lưu trạng thái job

Ví dụ schema SQL dùng các kiểu dữ liệu phổ biến. Cú pháp DDL và giới hạn độ dài cột cần được xác nhận trên database đang triển khai:

    CREATE TABLE artifact_job (
        job_id       VARCHAR(36) PRIMARY KEY,
        state        VARCHAR(16) NOT NULL,
        relative_path VARCHAR(512) NOT NULL,
        byte_count   BIGINT,
        sha256       CHAR(64),
        exit_code    INTEGER,
        error_code   VARCHAR(64),
        updated_at   TIMESTAMP NOT NULL
    );

Ý nghĩa các cột:

- `job_id`: idempotency key của yêu cầu logic.
- `state`: `PROCESSING`, `READY` hoặc `FAILED`.
- `relative_path`: đường dẫn tương đối bên dưới artifact root; tránh lưu đường dẫn tùy ý từ request.
- `byte_count`: số byte của artifact đã publish.
- `sha256`: checksum để kiểm tra tính toàn vẹn.
- `exit_code`: mã thoát của producer nếu process đã kết thúc.
- `error_code`: mã lỗi ngắn, không lưu secret hoặc nội dung nhạy cảm.
- `updated_at`: thời điểm trạng thái được cập nhật.

Đặt primary key trên `job_id` để database ngăn hai request tạo cùng một job. Nếu insert bị duplicate key, ứng dụng phải đọc trạng thái hiện có và quyết định trả kết quả, chờ job đang chạy hoặc phục hồi job cũ. Không tự động tạo job mới để né duplicate vì có thể chạy producer hai lần.

## 3. Tạo thư mục staging an toàn

Tạo một artifact root do ứng dụng quản lý, ví dụ:

    Path artifactRoot = Path.of("/var/lib/my-service/artifacts")
            .toAbsolutePath()
            .normalize();

Mỗi job có một thư mục riêng:

    Path jobDirectory = artifactRoot.resolve(jobId.toString())
            .normalize();

Trước khi tạo thư mục, xác nhận đường dẫn vẫn nằm dưới root:

    if (!jobDirectory.startsWith(artifactRoot)) {
        throw new SecurityException("Job path escapes artifact root");
    }

Dùng `Files.createDirectory(jobDirectory)` để yêu cầu thư mục mới và phát hiện ID đã tồn tại. Không dùng job ID do người dùng tùy ý nhập làm một phần path nếu chưa chuẩn hóa và xác thực. Cách đơn giản là ứng dụng sinh UUID, lưu lại và tái sử dụng UUID đó khi retry.

`normalize()` và `startsWith()` kiểm tra đường dẫn theo cấu trúc path, không tự giải quyết mọi tấn công qua symbolic link. Artifact root và các thư mục con phải do service account sở hữu, không cho người dùng không tin cậy tạo hoặc thay symbolic link bên trong. Nếu thư mục job đã tồn tại, dừng luồng tạo mới và tra cứu job cũ; không xóa hoặc ghi đè thư mục đó.

Cấu trúc thư mục:

    artifacts/
      4c2d.../
        stdout.raw
        stderr.log
        artifact.part
        artifact.bin

- `stdout.raw`: dữ liệu producer tạo ra.
- `stderr.log`: log chẩn đoán của producer.
- `artifact.part`: bản sao đang được kiểm tra.
- `artifact.bin`: artifact đã publish.

Giữ staging và final file trên cùng filesystem để có cơ hội dùng atomic move. Không đặt `artifact.part` trên một volume rồi move sang volume khác.

## 4. Ghi nhận trạng thái PROCESSING bằng transaction JDBC

Mở connection, tắt auto-commit, insert job và commit trước khi chạy process. Không giữ connection hoặc transaction mở trong suốt thời gian producer chạy vì điều đó chiếm connection pool và có thể giữ lock không cần thiết.

    static void insertProcessing(
            DataSource dataSource,
            UUID jobId,
            String relativePath
    ) throws SQLException {

        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);

            try (PreparedStatement statement = connection.prepareStatement("""
                    INSERT INTO artifact_job
                        (job_id, state, relative_path, updated_at)
                    VALUES (?, 'PROCESSING', ?, CURRENT_TIMESTAMP)
                    """)) {

                statement.setString(1, jobId.toString());
                statement.setString(2, relativePath);
                statement.executeUpdate();

                connection.commit();

            } catch (SQLException | RuntimeException | Error failure) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }
                throw failure;
            }
        }
    }

Một connection mới thường ở auto-commit mode. Sau khi gọi `setAutoCommit(false)`, thay đổi chỉ được lưu khi commit. Nếu có lỗi trước commit, rollback tường minh. JDBC quy định kết quả khi đóng connection còn transaction đang hoạt động là implementation-defined; không dựa vào `close()` để thay thế commit/rollback.

`PreparedStatement` dùng parameter binding cho job ID và đường dẫn. Không nối dữ liệu đầu vào vào SQL string. Bảng và tên cột ở ví dụ là cố định; nếu cần identifier động, xác thực allowlist và dùng API quote phù hợp của JDBC driver.

## 5. Khởi chạy producer bằng ProcessBuilder

Tạo command từ executable và từng argument riêng:

    List<String> command = List.of(
            "/opt/my-tools/exporter",
            "--format", "binary",
            "--scope", "daily"
    );

    ProcessBuilder builder = new ProcessBuilder(command);
    builder.directory(jobDirectory.toFile());
    builder.redirectOutput(stdoutFile.toFile());
    builder.redirectError(stderrFile.toFile());

Không truyền chuỗi kiểu `"/bin/sh -c ..."` hoặc `"cmd /c ..."` từ request. ProcessBuilder nhận executable và arguments riêng; không tự phân tích shell syntax. Nếu công cụ thực sự cần shell, command phải do ứng dụng cấu hình cố định và mọi đối số phải được xử lý theo quy tắc shell tương ứng.

Dùng redirect file cho cả stdout và stderr trong ví dụ này. Nếu chỉ đọc stdout mà bỏ mặc stderr pipe, producer có thể ghi đầy pipe stderr rồi bị block trong khi Java chờ stdout/process kết thúc. Redirect hai stream giúp tránh deadlock do ứng dụng không tiêu thụ pipe. Cần đặt quyền truy cập phù hợp cho log vì stderr có thể chứa đường dẫn, dữ liệu nghiệp vụ hoặc thông tin nhạy cảm.

Mặc định stdin của child là pipe do Java quản lý. Nếu producer không cần input, đóng `process.getOutputStream()` ngay sau `start()` để gửi EOF; nếu producer cần input, ghi đầy đủ dữ liệu rồi đóng stream. Nếu để stdin mở, công cụ đọc đến EOF có thể chờ vô hạn cho đến khi timeout.

Trước khi start, kiểm tra các file staging chưa tồn tại hoặc thuộc đúng job mới. ProcessBuilder redirect file sẽ tạo hoặc truncate file đích; không trỏ đến đường dẫn do người dùng tự chọn.

## 6. Timeout, exit code và giới hạn output

Không dùng `Thread.sleep()` để đo timeout. Dùng `System.nanoTime()` vì đây là đồng hồ đơn điệu thích hợp để đo thời lượng; `Instant.now()` có thể bị điều chỉnh theo đồng hồ hệ thống.

Ví dụ hàm chờ process có timeout và theo dõi kích thước output:

    static int waitForProducer(
            Process process,
            Path stdout,
            Path stderr,
            Duration timeout,
            long maxStdoutBytes,
            long maxStderrBytes
    ) throws IOException, InterruptedException, TimeoutException {

        long timeoutNanos = timeout.toNanos();
        long started = System.nanoTime();
        long pollNanos = TimeUnit.MILLISECONDS.toNanos(100);

        try {
            while (true) {
                long stdoutSize = Files.exists(stdout) ? Files.size(stdout) : 0;
                long stderrSize = Files.exists(stderr) ? Files.size(stderr) : 0;

                if (stdoutSize > maxStdoutBytes
                        || stderrSize > maxStderrBytes) {
                    stopProcess(process);
                    throw new IOException("Producer output limit exceeded");
                }

                long remaining = timeoutNanos
                        - (System.nanoTime() - started);

                if (remaining <= 0) {
                    stopProcess(process);
                    throw new TimeoutException("Producer timed out");
                }

                if (process.waitFor(
                        Math.min(remaining, pollNanos),
                        TimeUnit.NANOSECONDS
                )) {
                    break;
                }
            }

            long finalStdoutSize = Files.size(stdout);
            long finalStderrSize = Files.size(stderr);

            if (finalStdoutSize > maxStdoutBytes
                    || finalStderrSize > maxStderrBytes) {
                throw new IOException("Producer output limit exceeded");
            }

            return process.exitValue();

        } catch (InterruptedException interrupted) {
            terminateUninterruptibly(process);
            throw interrupted;

        } catch (IOException | TimeoutException | RuntimeException failure) {
            if (process.isAlive()) {
                try {
                    stopProcess(process);
                } catch (InterruptedException interrupted) {
                    terminateUninterruptibly(process);
                    interrupted.addSuppressed(failure);
                    throw interrupted;
                }
            }
            throw failure;
        }
    }

Hàm dừng process theo hai giai đoạn:

    static void stopProcess(Process process)
            throws InterruptedException {

        process.destroy();

        if (!process.waitFor(2, TimeUnit.SECONDS)) {
            process.destroyForcibly();
            process.waitFor();
        }
    }

`destroy()` yêu cầu process kết thúc; hành vi cụ thể phụ thuộc hệ điều hành và implementation. Nếu process không kết thúc trong grace period, `destroyForcibly()` yêu cầu dừng cưỡng bức. Sau đó vẫn phải chờ process thực sự kết thúc trước khi đọc exit code hoặc xử lý file output.

Kiểm tra file size mỗi 100 ms chỉ là giới hạn best-effort: producer có thể ghi vượt ngưỡng giữa hai lần polling. Nếu yêu cầu giới hạn cứng, cần thêm quota ở filesystem/container/OS hoặc thiết kế pipe pump có giới hạn byte và xử lý stdout/stderr đồng thời. Không coi polling file size là một cơ chế quota tuyệt đối.

Nếu producer tạo child process hoặc daemon, dừng Process trực tiếp không bảo đảm toàn bộ descendants kết thúc. Khi hợp đồng công cụ cho phép sinh process con, cần theo dõi process tree và có chính sách dừng riêng; `ProcessHandle.descendants()` chỉ trả snapshot có thể thay đổi.

Producer cũng cần có hợp đồng rằng khi process chính thoát, không còn child process tiếp tục ghi vào `stdout.raw`. Nếu công cụ tách child chạy nền, phải đợi child hoàn tất hoặc dùng cơ chế supervisor/process group của hệ điều hành trước khi coi file staging là ổn định.

### Xử lý interruption

Nếu thread đang chờ process bị interrupt, dừng process và chờ nó kết thúc trước khi truyền interruption lên tầng gọi. Không nuốt `InterruptedException`.

    static void terminateUninterruptibly(Process process) {
        process.destroyForcibly();

        boolean interruptedAgain = false;

        while (process.isAlive()) {
            try {
                process.waitFor();
            } catch (InterruptedException ignored) {
                interruptedAgain = true;
                process.destroyForcibly();
            }
        }

        if (interruptedAgain) {
            Thread.currentThread().interrupt();
        }
    }

Trong orchestration code, khi bắt `InterruptedException`, có thể tạm clear interrupt status bằng `Thread.interrupted()` để ghi trạng thái job thất bại vào database, rồi khôi phục cờ interrupt trong `finally` trước khi ném exception lên. Chỉ làm điều này sau khi process đã được dừng và không còn thao tác ngoài cần chờ.

## 7. Dùng Process.close() trong JDK 26

Từ JDK 26, `java.lang.Process` triển khai `Closeable` và `AutoCloseable`. Có thể dùng try-with-resources:

    Process process = builder.start();

    try (process) {
        int exitCode = waitForProducer(
                process,
                stdoutFile,
                stderrFile,
                Duration.ofMinutes(2),
                500L * 1024 * 1024,
                10L * 1024 * 1024
        );

        if (exitCode != 0) {
            throw new IOException(
                    "Producer exited with code " + exitCode
            );
        }
    }

`Process.close()` đóng các reader/writer stream và chờ process kết thúc. Nếu bị interrupt trong lúc chờ, close yêu cầu kết thúc cưỡng bức và tiếp tục đợi process kết thúc, sau đó khôi phục interrupt status. Close là idempotent theo API.

Trong ví dụ này, stdout và stderr đã được redirect ra file nên Java không cần đọc pipe. Nếu dùng pipe thay vì redirect, phải tiêu thụ dữ liệu trước khi gọi close. API nêu rõ nội dung stream chưa đọc đến EOF có thể bị loại bỏ khi close. Nếu cần exit code, chờ process kết thúc và lấy exit code trước khi close.

Không giả định process tự kết thúc khi không còn reference Java. Process có thể tiếp tục chạy bất đồng bộ; cần đóng tường minh và kiểm tra trạng thái.

## 8. Đọc file staging và sao chép bằng FileChannel

Sau khi producer kết thúc với exit code 0, file stdout mới được xem là đầu vào hợp lệ. Mở file nguồn chỉ đọc và file `artifact.part` với `CREATE_NEW` để tránh ghi đè file khác.

Khi sao chép, tính SHA-256 trên đúng byte được ghi. `FileChannel.read()` và `write()` có thể xử lý ít byte hơn buffer yêu cầu; luôn lặp đến khi buffer được ghi hết.

    record FileMetadata(long byteCount, String sha256) {}

    static FileMetadata copyAndHash(
            Path source,
            Path target,
            long maxBytes
    ) throws IOException, NoSuchAlgorithmException {

        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        ByteBuffer buffer = ByteBuffer.allocateDirect(64 * 1024);
        long total = 0;

        try (FileChannel input = FileChannel.open(
                    source,
                    StandardOpenOption.READ
             );
             FileChannel output = FileChannel.open(
                    target,
                    StandardOpenOption.CREATE_NEW,
                    StandardOpenOption.WRITE
             )) {

            while (true) {
                buffer.clear();

                int count = input.read(buffer);
                if (count < 0) {
                    break;
                }
                if (count == 0) {
                    continue;
                }

                total += count;
                if (total > maxBytes) {
                    throw new IOException("Artifact exceeds size limit");
                }

                buffer.flip();

                // Digest nhận bản sao read-only để không đổi position
                // của buffer đang được dùng ghi file.
                digest.update(buffer.asReadOnlyBuffer());

                while (buffer.hasRemaining()) {
                    output.write(buffer);
                }
            }

            output.force(true);
        }

        return new FileMetadata(
                total,
                HexFormat.of().formatHex(digest.digest())
        );
    }

`force(true)` yêu cầu đẩy cả nội dung file và metadata liên quan ra storage device. Bảo đảm mạnh nhất được tài liệu API nêu cho file nằm trên local storage; với network filesystem, không có cùng bảo đảm. `force()` cũng chỉ bảo đảm thay đổi được thực hiện qua FileChannel hoặc các stream/RandomAccessFile liên quan được quy định, không phải mọi thay đổi từ process ngoài hoặc mọi memory-mapped buffer.

Trong pipeline này, producer đã ghi vào `stdout.raw`; FileChannel sao chép nội dung đó sang `artifact.part` và force file đích. Đây là bước làm cho file artifact do Java quản lý có thể được kiểm tra và publish. Nếu yêu cầu chống mất dữ liệu khi mất điện, cần kiểm tra thêm semantics của filesystem/storage và cách đồng bộ directory entry sau rename; Java không cung cấp một cơ chế portable để fsync thư mục cha trên mọi hệ điều hành.

SHA-256 giúp phát hiện thay đổi ngoài ý muốn khi kiểm tra lại artifact. Nếu kẻ tấn công có thể sửa cả file lẫn row checksum trong database, hash không chứng minh nguồn gốc; dùng HMAC hoặc chữ ký số với khóa được bảo vệ nếu threat model yêu cầu xác thực.

## 9. Publish file bằng atomic move

Sau khi copy thành công, checksum được tính và `force(true)` hoàn tất, đổi tên file tạm thành file chính thức:

    Path finalFile = jobDirectory.resolve("artifact.bin");

    Files.move(
            partFile,
            finalFile,
            StandardCopyOption.ATOMIC_MOVE
    );

Dùng source và target trong cùng job directory để tránh chuyển qua filesystem khác. Nếu filesystem không hỗ trợ atomic move, `Files.move` có thể ném `AtomicMoveNotSupportedException`. Với pipeline yêu cầu không bao giờ lộ file một phần, hãy fail và xử lý recovery; không tự fallback sang copy thường rồi tuyên bố vẫn atomic.

Tên file cuối cùng là duy nhất theo job ID. Không dùng `REPLACE_EXISTING` nếu không có chính sách overwrite rõ ràng. Nếu file đích đã tồn tại, cần kiểm tra xem đó là kết quả của lần chạy trước, một job trùng ID hay dữ liệu không thuộc ứng dụng.

Atomic move chỉ bảo đảm tính nguyên tử của thao tác đổi tên theo khả năng filesystem; nó không tạo transaction chung với database và không tự đảm bảo directory entry đã bền vững qua mọi loại mất điện.

## 10. Cập nhật READY bằng transaction JDBC

Chỉ sau khi file cuối cùng đã tồn tại mới cập nhật database sang `READY`. Transaction cập nhật metadata phải kiểm tra đúng một row `PROCESSING` được chuyển trạng thái:

    static void markReady(
            DataSource dataSource,
            UUID jobId,
            FileMetadata metadata,
            int exitCode
    ) throws SQLException {

        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);

            try (PreparedStatement statement = connection.prepareStatement("""
                    UPDATE artifact_job
                       SET state = 'READY',
                           byte_count = ?,
                           sha256 = ?,
                           exit_code = ?,
                           updated_at = CURRENT_TIMESTAMP
                     WHERE job_id = ?
                       AND state = 'PROCESSING'
                    """)) {

                statement.setLong(1, metadata.byteCount());
                statement.setString(2, metadata.sha256());
                statement.setInt(3, exitCode);
                statement.setString(4, jobId.toString());

                int updated = statement.executeUpdate();
                if (updated != 1) {
                    throw new SQLException(
                            "Expected one PROCESSING row, updated=" + updated
                    );
                }

                connection.commit();

            } catch (SQLException | RuntimeException | Error failure) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }
                throw failure;
            }
        }
    }

Điều kiện `WHERE state = 'PROCESSING'` giúp tránh ghi đè một trạng thái đã thay đổi bởi worker khác. Nếu update count bằng 0, cần đọc lại job state và điều tra race/retry; không giả định database đã ghi READY.

Không giữ connection JDBC trong lúc producer chạy hoặc lúc copy file lớn. Chỉ mở connection cho các giao dịch ngắn: tạo row PROCESSING, chuyển READY hoặc FAILED. Điều này giảm thời gian giữ connection và lock.

## 11. Đánh dấu FAILED và xử lý lỗi

Nếu producer timeout, exit code khác 0, output vượt giới hạn hoặc FileChannel copy thất bại trước khi publish, cập nhật trạng thái FAILED:

    static void markFailed(
            DataSource dataSource,
            UUID jobId,
            String errorCode
    ) throws SQLException {

        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);

            try (PreparedStatement statement = connection.prepareStatement("""
                    UPDATE artifact_job
                       SET state = 'FAILED',
                           error_code = ?,
                           updated_at = CURRENT_TIMESTAMP
                     WHERE job_id = ?
                       AND state = 'PROCESSING'
                    """)) {

                statement.setString(1, errorCode);
                statement.setString(2, jobId.toString());
                int updated = statement.executeUpdate();
                if (updated != 1) {
                    throw new SQLException("Could not mark job FAILED");
                }
                connection.commit();

            } catch (SQLException | RuntimeException | Error failure) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }
                throw failure;
            }
        }
    }

Lưu mã lỗi ngắn như `PROCESS_TIMEOUT`, `PROCESS_EXIT_NONZERO`, `OUTPUT_LIMIT` hoặc `FILE_COPY_FAILED`. Tránh ghi toàn bộ command line, environment, password, token hay stderr vào bảng trạng thái. Log file có thể được bảo vệ riêng và có retention policy.

Nếu cập nhật FAILED cũng thất bại do database không khả dụng, row vẫn có thể ở PROCESSING. Đây là lý do reconciliation cần xử lý các row stale; không giả định catch block luôn có thể ghi trạng thái lỗi.

## 12. Tích hợp orchestration

Luồng điều phối ở mức ứng dụng có thể viết như sau. Các hàm `insertProcessing`, `waitForProducer`, `copyAndHash`, `markReady` và `markFailed` là các hàm đã trình bày ở trên:

    static ArtifactResult runExport(
            DataSource dataSource,
            Path artifactRoot,
            UUID jobId,
            List<String> command,
            Duration timeout,
            long maxOutputBytes,
            long maxErrorBytes
    ) throws Exception {

        if (timeout.isZero() || timeout.isNegative()) {
            throw new IllegalArgumentException("timeout must be positive");
        }
        // Validate conversion before starting a native process.
        timeout.toNanos();
        if (maxOutputBytes < 0 || maxErrorBytes < 0) {
            throw new IllegalArgumentException("Output limits must be non-negative");
        }

        Path root = artifactRoot.toAbsolutePath().normalize();
        Files.createDirectories(root);

        Path jobDirectory = root.resolve(jobId.toString()).normalize();
        if (!jobDirectory.startsWith(root)) {
            throw new SecurityException("Invalid job directory");
        }

        Files.createDirectory(jobDirectory);

        Path rawFile = jobDirectory.resolve("stdout.raw");
        Path errorFile = jobDirectory.resolve("stderr.log");
        Path partFile = jobDirectory.resolve("artifact.part");
        Path finalFile = jobDirectory.resolve("artifact.bin");

        String relativePath = jobId + "/artifact.bin";

    // Caller phải tra cứu jobId trước khi gọi để xử lý retry/duplicate.
    // Hàm này chỉ minh họa đường chạy cho một job mới.

        try {
            insertProcessing(dataSource, jobId, relativePath);
        } catch (SQLException databaseFailure) {
            try {
                Files.deleteIfExists(jobDirectory);
            } catch (IOException cleanupFailure) {
                databaseFailure.addSuppressed(cleanupFailure);
            }
            throw databaseFailure;
        }

        boolean published = false;

        try {
            ProcessBuilder builder = new ProcessBuilder(command)
                    .directory(jobDirectory.toFile())
                    .redirectOutput(rawFile.toFile())
                    .redirectError(errorFile.toFile());

            Process process = builder.start();

            int exitCode;
            try (process) {
                // Producer không nhận dữ liệu từ stdin trong kịch bản này.
                process.getOutputStream().close();

                exitCode = waitForProducer(
                        process,
                        rawFile,
                        errorFile,
                        timeout,
                        maxOutputBytes,
                        maxErrorBytes
                );
            }

            if (exitCode != 0) {
                throw new IOException(
                        "Producer exited with code " + exitCode
                );
            }

            FileMetadata metadata = copyAndHash(
                    rawFile,
                    partFile,
                    maxOutputBytes
            );

            Files.move(
                    partFile,
                    finalFile,
                    StandardCopyOption.ATOMIC_MOVE
            );
            published = true;

            // Nếu commit không xác định, giữ row PROCESSING để recovery
            // kiểm tra file và trạng thái database sau đó.
            markReady(dataSource, jobId, metadata, exitCode);

            try {
                Files.deleteIfExists(rawFile);
            } catch (IOException cleanupFailure) {
                System.err.println(
                        "Staging cleanup deferred for job " + jobId
                );
            }

            return new ArtifactResult(
                    jobId,
                    relativePath,
                    metadata.byteCount(),
                    metadata.sha256()
            );

        } catch (InterruptedException interrupted) {
            // InterruptedException đã clear interrupt status. Ghi FAILED
            // best-effort, sau đó khôi phục trạng thái interrupt.
            Thread.interrupted();

            try {
                if (!published) {
                    markFailed(dataSource, jobId, "INTERRUPTED");
                }
            } catch (SQLException databaseFailure) {
                interrupted.addSuppressed(databaseFailure);
            } finally {
                Thread.currentThread().interrupt();
            }

            throw interrupted;

        } catch (ClosedByInterruptException interruptedIo) {
            // FileChannel là interruptible; channel có thể đã đóng. Clear cờ
            // tạm để ghi FAILED và dọn part, rồi khôi phục interrupt status.
            Thread.interrupted();

            try {
                if (!published) {
                    markFailed(dataSource, jobId, "INTERRUPTED_IO");
                    Files.deleteIfExists(partFile);
                }
            } catch (Exception cleanupFailure) {
                interruptedIo.addSuppressed(cleanupFailure);
            } finally {
                Thread.currentThread().interrupt();
            }

            throw interruptedIo;

        } catch (Exception failure) {
            // Bảo vệ trường hợp filesystem đã hoàn tất rename nhưng lời gọi
            // trả lỗi không xác định; giữ job để reconciliation kiểm tra.
            if (!published) {
                try {
                    published = Files.exists(finalFile);
                } catch (SecurityException checkFailure) {
                    failure.addSuppressed(checkFailure);
                }
            }

            if (!published) {
                try {
                    markFailed(
                            dataSource,
                            jobId,
                            failure.getClass().getSimpleName()
                    );
                } catch (SQLException databaseFailure) {
                    failure.addSuppressed(databaseFailure);
                }

                try {
                    Files.deleteIfExists(partFile);
                } catch (IOException cleanupFailure) {
                    failure.addSuppressed(cleanupFailure);
                }
            }

            // Nếu file đã publish nhưng markReady thất bại, giữ trạng thái
            // PROCESSING để reconciliation xác minh, không đánh dấu FAILED.
            throw failure;
        }
    }

    record ArtifactResult(
            UUID jobId,
            String relativePath,
            long byteCount,
            String sha256
    ) {}

Đây là skeleton tích hợp để thể hiện thứ tự và ranh giới lỗi; cần bổ sung constructor/configuration của DataSource, schema theo database, logging, metric và policy retry của hệ thống thực tế. Nếu lỗi xảy ra sau atomic move nhưng trước khi commit READY, file cuối cùng vẫn tồn tại và row có thể còn PROCESSING. Không xóa file đó trong catch block vì có thể database đã commit thành công nhưng client mất kết nối trước khi nhận xác nhận.

### Lưu ý về interruption trong process wait

Nếu `waitForProducer` bị interrupt, hàm cần dừng process trước khi ném `InterruptedException`. Trong triển khai thực tế, bọc phần chờ bằng catch để gọi `terminateUninterruptibly(process)` như phần trước. Không để `Process.close()` là cơ chế duy nhất dừng process nếu orchestration cần ghi FAILED trước khi thoát.

## 13. Vì sao file và database không cùng transaction?

Filesystem và JDBC database là hai resource manager độc lập. Một lần `Files.move(..., ATOMIC_MOVE)` không tham gia transaction JDBC. Nếu cập nhật database và đổi tên file theo hai thứ tự khác nhau, luôn có một khoảng thời gian có thể xảy ra lỗi:

| Thời điểm lỗi | File | Database | Cách phục hồi |
|---|---|---|---|
| Trước khi process kết thúc | Chỉ có stdout staging | PROCESSING | Dừng process, đánh FAILED hoặc retry theo idempotency |
| Sau process, trước copy | stdout.raw hoàn chỉnh | PROCESSING | Xác minh exit code rồi tiếp tục copy hoặc chạy lại theo policy |
| Trong lúc copy | artifact.part chưa hoàn chỉnh | PROCESSING | Xóa part dở, copy lại từ raw |
| Sau force, trước move | artifact.part hoàn chỉnh | PROCESSING | Kiểm tra checksum rồi publish hoặc copy lại |
| Sau atomic move, trước DB commit | artifact.bin tồn tại | PROCESSING | Reconciliation kiểm tra file, tính lại hash rồi cập nhật READY |
| Sau DB commit, trước khi client nhận response | artifact.bin tồn tại | READY | Client truy vấn lại theo job ID, không tạo job mới |
| File bị mất/hỏng sau READY | Thiếu hoặc checksum không khớp | READY | Đánh dấu CORRUPT/REPAIR, không trả file như hợp lệ |

Không tuyên bố pipeline có tính atomic end-to-end. Thiết kế ở đây là một workflow có trạng thái bền vững và khả năng phục hồi. Nếu cần giao dịch phân tán giữa database và object storage, cần một giao thức/transaction coordinator hoặc kiến trúc lưu trữ phù hợp; JDBC commit đơn lẻ không giải quyết được.

## 14. Reconciliation và idempotency

Một worker định kỳ quét các job ở trạng thái PROCESSING quá thời hạn. Trước khi thay đổi trạng thái, phải xác minh không còn worker/process đang sở hữu job đó. Có thể dùng lease/heartbeat trong database để tránh hai worker phục hồi cùng một job.

Trong production, nên mở rộng schema với `owner_id`, `lease_until`, `process_pid` và thời điểm process bắt đầu. Lease giúp worker khác biết khi nào có thể nhận phục hồi; PID chỉ là dữ liệu chẩn đoán vì hệ điều hành có thể tái sử dụng PID. Nếu cần xác định một process còn sống sau khi JVM owner crash, đối chiếu thêm thời điểm bắt đầu và thông tin executable từ `ProcessHandle.Info`, hoặc dùng supervisor/container/job object của hệ điều hành. Không kết luận ownership chỉ từ PID.

Quy tắc phục hồi gợi ý:

1. **PROCESSING, không có final file, process đã chết:** kiểm tra stdout.raw và exit metadata; tiếp tục copy nếu dữ liệu đáng tin cậy, hoặc chạy lại producer nếu command idempotent.
2. **PROCESSING, có artifact.bin:** tính lại kích thước và SHA-256; nếu khớp chính sách, chuyển READY bằng transaction; nếu không, cách ly file và đánh dấu cần sửa.
3. **READY, file tồn tại:** kiểm tra kích thước/checksum theo chính sách audit.
4. **READY, file thiếu hoặc checksum sai:** không trả file; chuyển trạng thái CORRUPT/REPAIR bằng workflow có kiểm soát.
5. **File tồn tại nhưng không có row:** xem là orphan; cách ly hoặc xóa sau thời gian grace period và xác minh không có job đang commit.
6. **FAILED có file .part:** xóa file tạm theo retention policy; giữ log lỗi trong khoảng thời gian phục vụ điều tra.

Idempotency cần được xác định theo nghiệp vụ. Nếu producer chỉ xuất dữ liệu từ nguồn đọc, có thể chạy lại với cùng snapshot/version. Nếu producer gửi lệnh thanh toán, gửi email hoặc cập nhật hệ thống khác, chạy lại có thể tạo side effect trùng. Dùng idempotency key xuyên suốt, hoặc tách phần tạo artifact khỏi side effect không idempotent.

Không dùng timestamp file hoặc sự tồn tại của file đơn lẻ làm bằng chứng job đã hoàn thành. Database state, checksum và lease/ownership phải cùng tham gia quyết định.

## 15. Quản lý vòng đời JDBC và thứ tự đóng resource

Các tài nguyên JDBC như Connection, PreparedStatement và ResultSet đều nên được đóng bằng try-with-resources. Đóng theo thứ tự ngược với lúc mở: ResultSet, Statement rồi Connection.

    try (Connection connection = dataSource.getConnection();
         PreparedStatement statement =
                 connection.prepareStatement("SELECT state FROM artifact_job WHERE job_id = ?")) {

        statement.setString(1, jobId.toString());

        try (ResultSet resultSet = statement.executeQuery()) {
            if (resultSet.next()) {
                String state = resultSet.getString("state");
            }
        }
    }

Với transaction ghi dữ liệu:

- Tắt auto-commit trước khi thực hiện nhóm câu lệnh.
- Commit chỉ khi mọi thao tác của transaction thành công.
- Rollback khi lỗi.
- Đóng statement/result set trước connection.
- Không để transaction mở trong lúc process chạy hoặc file lớn đang được copy.
- Không giả định connection pool tự rollback transaction trong mọi trường hợp nếu ứng dụng không làm đúng hợp đồng.

JDBC 4.5 MR5 trong JDK 26 bổ sung `AutoCloseable` cho `Array`, `Blob`, `Clob`, `NClob` và `SQLXML`. Nếu pipeline lưu LOB, đóng chúng bằng try-with-resources và kiểm tra driver có dùng locator gắn với transaction/connection hay không. Driver và database phải hỗ trợ kiểu dữ liệu cụ thể.

## 16. Giới hạn tài nguyên và bảo mật

Một pipeline xuất file có thể làm cạn disk, connection pool, process slots hoặc log storage. Cần giới hạn từng loại:

| Tài nguyên | Biện pháp |
|---|---|
| Process | Timeout, giới hạn số process đồng thời và dừng khi vượt hạn mức |
| stdout artifact | Giới hạn byte, quota filesystem và retention |
| stderr log | Giới hạn byte, quyền file và chính sách xóa |
| FileChannel | Đóng tường minh, tránh giữ channel/lock qua transaction |
| Database | Pool size, acquisition timeout, query timeout và transaction ngắn |
| Disk | Kiểm tra dung lượng trống, dọn staging/orphan theo tuổi và trạng thái |
| Retry | Số lần retry hữu hạn, backoff và idempotency key |
| Command | Executable allowlist, arguments riêng, environment tối thiểu |
| Path | Root cố định, UUID job, normalize và kiểm tra startsWith(root) |

Không ghi password, access token, private key hoặc toàn bộ environment vào log. Không lấy command từ một chuỗi do người dùng cung cấp rồi chuyển vào shell. Nếu process cần credential, truyền qua secret manager hoặc cơ chế credential an toàn của môi trường; tránh đưa bí mật lên command line vì có thể bị quan sát qua process inspection.

Đặt quyền thư mục job để chỉ service account cần thiết có thể đọc. Khi phục vụ artifact, kiểm tra quyền người dùng trên database/application; UUID khó đoán không phải cơ chế phân quyền.

## 17. Kiểm thử tích hợp và lỗi có chủ đích

Chạy các test trong database staging và filesystem riêng:

| Test | Cách tạo tình huống | Kết quả mong đợi |
|---|---|---|
| Thành công | Producer exit 0 và ghi file hợp lệ | File artifact có checksum; DB READY |
| Exit code khác 0 | Producer trả mã lỗi | DB FAILED; không có artifact READY |
| Timeout | Producer chạy lâu hơn deadline | Process bị dừng; DB FAILED |
| stdout quá lớn | Producer ghi vượt max bytes | Process dừng; job FAILED; không publish |
| stderr quá lớn | Producer spam log | Process dừng; log không chiếm disk vô hạn |
| Copy lỗi | Hết disk hoặc permission bị từ chối | Không có READY; part được cleanup/reconcile |
| Atomic move không hỗ trợ | Dùng filesystem không hỗ trợ ATOMIC_MOVE | Không fallback âm thầm; job giữ trạng thái có thể phục hồi |
| DB insert lỗi | Tắt database trước khi tạo PROCESSING | Không chạy producer |
| DB commit READY lỗi | Ngắt DB sau khi file đã publish | File giữ lại; row PROCESSING được reconciliation |
| Process interruption | Interrupt worker khi đang chờ | Process được dừng, trạng thái được ghi best-effort |
| Duplicate job ID | Gửi cùng idempotency key hai lần | Không chạy producer trùng; đọc trạng thái job hiện có |
| Corrupt artifact | Thay đổi một byte sau publish | Checksum không khớp; không phục vụ file như hợp lệ |
| Crash recovery | Dừng JVM tại từng ranh giới trạng thái | Recovery phân loại staging, final file và database row đúng |

Không chỉ test happy path. Các lỗi sau atomic move và trong lúc commit là nơi dễ tạo file mồ côi hoặc row sai trạng thái nhất.

## 18. Quan sát và vận hành

Ghi log theo job ID để nối sự kiện giữa process, file và database. Các trường có ích:

- Job ID và state transition.
- Process PID, executable name đã allowlist và exit code.
- Thời gian chạy, timeout, số byte stdout/stderr.
- Artifact relative path, byte count và SHA-256.
- Thời gian copy, force, atomic move và JDBC commit.
- SQLState/vendor code nếu JDBC lỗi.
- Số lần retry và kết quả reconciliation.

Không log dữ liệu nhạy cảm của artifact hoặc nội dung stdout chỉ để tiện debug. Dùng metric tổng hợp để theo dõi:

- Số job PROCESSING/READY/FAILED và số PROCESSING quá hạn.
- Process chạy đồng thời, timeout và exit code khác 0.
- Tổng byte staging/final, dung lượng disk và số orphan.
- JDBC connection wait, transaction duration, rollback và commit failure.
- Checksum mismatch và số lần recovery thành công/thất bại.

Nếu job PROCESSING tăng liên tục, có thể producer bị treo, process cleanup thất bại, database commit không hoàn tất hoặc worker reconciliation không chạy. Đừng chỉ tăng timeout trước khi xác định nguyên nhân.

## 19. Quy trình thực hành

1. Tạo bảng `artifact_job` trong database staging.
2. Tạo artifact root có quyền truy cập giới hạn.
3. Chọn một producer test có output xác định và exit code có thể điều khiển.
4. Tạo UUID job và commit row PROCESSING bằng JDBC.
5. Khởi chạy producer với ProcessBuilder và redirect stdout/stderr vào thư mục job.
6. Áp dụng timeout, giới hạn output và xử lý exit code.
7. Đọc stdout.raw bằng FileChannel, tính SHA-256 và ghi artifact.part.
8. Gọi `force(true)`, đóng channel rồi atomic move thành artifact.bin.
9. Mở transaction JDBC ngắn, cập nhật READY và commit.
10. Kiểm tra file, kích thước, checksum và row database.
11. Thử exit code lỗi, timeout, output quá lớn, disk error và DB commit failure.
12. Viết reconciliation cho job PROCESSING quá hạn và file orphan.
13. Kiểm tra shutdown khi còn process chạy và khi JDBC transaction đang mở.
14. Chạy lại trên đúng JDK/vendor, filesystem và JDBC driver của môi trường triển khai.

## 20. Checklist trước khi đưa vào production

- [ ] Command được tạo từ executable/argument allowlist, không nối chuỗi shell từ input.
- [ ] Process có timeout, output cap và chính sách dừng rõ ràng.
- [ ] stdout/stderr được redirect hoặc tiêu thụ đồng thời để tránh pipe deadlock.
- [ ] Process được chờ kết thúc và exit code được kiểm tra trước khi chấp nhận output.
- [ ] Dùng Process.close() trên JDK 26 sau khi đã đọc dữ liệu cần thiết.
- [ ] File staging/final nằm dưới root do ứng dụng quản lý.
- [ ] FileChannel xử lý partial read/write và đóng tường minh.
- [ ] SHA-256 tính trên byte thực tế đã ghi.
- [ ] force(true) được dùng đúng phạm vi; hiểu giới hạn local/network filesystem.
- [ ] Atomic move được kiểm tra trên filesystem đích; không fallback âm thầm nếu yêu cầu atomic.
- [ ] JDBC transaction commit/rollback tường minh; không giữ connection trong lúc process/file I/O chạy lâu.
- [ ] READY chỉ được commit sau khi artifact đã publish.
- [ ] Lỗi sau publish trước commit được xử lý bằng reconciliation, không xóa file mù quáng.
- [ ] Job ID có unique constraint và retry có idempotency policy.
- [ ] Có cleanup cho .part, stdout.raw, stderr.log và orphan theo retention.
- [ ] Có test interruption, timeout, duplicate request, DB outage và crash recovery.

## 21. Trạng thái API và khả năng tương thích JDK

| API/tính năng | Trạng thái | Ghi chú |
|---|---|---|
| ProcessBuilder / Process.waitFor / destroy | Stable | Dùng để tạo, chờ và dừng process |
| Process.close() | Stable, Since 26 | Đóng stream và chờ process kết thúc |
| FileChannel / force / transferTo | Stable | Có từ các JDK trước; semantics phụ thuộc filesystem/storage |
| JDBC Connection / transaction / PreparedStatement | Stable | Transaction và driver semantics cần kiểm thử |
| JDBC 4.5 MR5 | API chuẩn trong JDK 26 | Tính năng tùy chọn vẫn phụ thuộc driver/database |
| try-with-resources / AutoCloseable | Stable | Đóng tài nguyên theo thứ tự ngược |
| Virtual threads | Stable từ JDK 21 | Có thể dùng cho I/O orchestration; vẫn giới hạn process/DB/disk riêng |

Không cần preview flag cho các ví dụ của bài này. Nếu nâng lên JDK 27, kiểm tra lại JDBC driver, provider và runtime support theo ma trận chính thức của nhà cung cấp; không dùng API nội bộ hoặc phụ thuộc preview để quản lý tài nguyên.

## Tài liệu chính thức

- [Java SE 26 API — Process](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Process.html): `Process.close()`, stream, waitFor, exitValue và dừng process; close được bổ sung từ JDK 26.
- [Java SE 26 API — ProcessBuilder](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ProcessBuilder.html): command, working directory, environment và redirect stdout/stderr.
- [Java SE 26 API — ProcessHandle](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ProcessHandle.html): PID, children, descendants và quan sát process tree.
- [Java SE 26 API — FileChannel](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/FileChannel.html): positional I/O, transfer, force, file lock và semantics của channel.
- [Java SE 26 API — Files](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Files.html): tạo thư mục, move, atomic move và file operations.
- [Java SE 26 API — Connection](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/Connection.html): auto-commit, commit, rollback và close.
- [Java SE 26 API — PreparedStatement](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/PreparedStatement.html): parameter binding và thực thi câu lệnh có tham số.
- [Java SE 26 API — DataSource](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/javax/sql/DataSource.html): lấy connection từ nguồn dữ liệu.
- [Java SE 26 API — java.sql package](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/package-summary.html): JDBC 4.5 MR5 và các cập nhật chuẩn trong JDK 26.
- [Java SE 26 API — AutoCloseable](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/AutoCloseable.html): hợp đồng close và try-with-resources.
- [Oracle — JDK 26 Release Notes](https://www.oracle.com/java/technologies/javase/26-relnote-issues.html): Process AutoCloseable và các cập nhật JDBC 4.5.
- [Java SE 26 API — MessageDigest](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/MessageDigest.html): tính digest SHA-256 để kiểm tra tính toàn vẹn.

Bài thực hành này dùng Process để kiểm soát chương trình ngoài, FileChannel để tạo artifact có checksum và force, và JDBC để lưu trạng thái có transaction. Thiết kế không giả định filesystem và database commit cùng lúc; trạng thái PROCESSING cùng reconciliation giúp phục hồi sau timeout, lỗi I/O hoặc crash giữa các bước.
