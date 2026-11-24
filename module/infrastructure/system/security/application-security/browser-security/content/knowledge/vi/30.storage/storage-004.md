# IndexedDB: lưu trữ dữ liệu có cấu trúc trong trình duyệt

Ứng dụng web thường cần giữ dữ liệu sau khi người dùng tải lại trang hoặc mất kết nối. Ví dụ, một trình soạn thảo có thể lưu bản nháp, ứng dụng quản lý công việc có thể lưu danh sách đang chờ đồng bộ, còn ứng dụng offline cần giữ dữ liệu và tài nguyên để tiếp tục hoạt động khi mạng không sẵn sàng.

IndexedDB là cơ sở dữ liệu hướng đối tượng, bất đồng bộ, được tích hợp trong trình duyệt. Nó lưu các bản ghi có cấu trúc theo origin và hỗ trợ object store, index, transaction, truy vấn theo khóa và dữ liệu có thể biểu diễn bằng structured clone. IndexedDB phù hợp với dữ liệu ứng dụng có cấu trúc và dung lượng lớn hơn những gì nên lưu trong localStorage.

Tuy nhiên, dữ liệu trình duyệt có thể bị xóa khi người dùng xóa site data, khi trình duyệt thu hồi dữ liệu best-effort do áp lực dung lượng hoặc khi môi trường duyệt thay đổi. IndexedDB cũng không phải kho bí mật: JavaScript chạy được trong cùng origin, chẳng hạn mã XSS, có thể đọc dữ liệu mà ứng dụng lưu ở đó.

Bài học này tập trung vào IndexedDB, đồng thời đặt nó trong hệ sinh thái Storage APIs: Cache API, quota, eviction và cách bảo vệ dữ liệu nhạy cảm.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích IndexedDB và chọn nó cho dữ liệu có cấu trúc.
- Phân biệt IndexedDB với localStorage, Cache API và HTTP cache.
- Thiết kế database, object store, key, index và transaction.
- Tạo hoặc nâng cấp schema bằng versionchange transaction.
- Đọc, ghi, xóa và duyệt bản ghi bất đồng bộ.
- Xử lý transaction lifecycle, lỗi, blocked upgrade và connection version change.
- Ước lượng quota, yêu cầu persistent storage và xử lý QuotaExceededError.
- Giải thích eviction và giới hạn của việc lưu trữ offline.
- Dùng Cache API cho tài nguyên phù hợp và quản lý cache version.
- Nhận diện rủi ro khi lưu token, thông tin cá nhân hoặc dữ liệu nhạy cảm.
- Thiết kế logout, account switching, data minimization và đồng bộ an toàn.
- Kiểm thử IndexedDB và Cache Storage bằng DevTools.

## 1. Browser storage và vị trí của IndexedDB

Trình duyệt cung cấp nhiều cơ chế lưu trữ. Chúng khác nhau về kiểu dữ liệu, API, giới hạn và cách sử dụng.

| Cơ chế | Dữ liệu phù hợp | Đặc điểm |
|---|---|---|
| Cookies | Session identifier và một số trạng thái cần gửi kèm request | Có thể được gửi tự động đến server; cần cấu hình Secure, HttpOnly, SameSite và Path/Domain phù hợp |
| localStorage | Cấu hình nhỏ, chuỗi đơn giản | Đồng bộ, chỉ lưu string, dễ chặn main thread nếu thao tác nhiều |
| sessionStorage | Trạng thái nhỏ theo tab/session | Đồng bộ, thường kết thúc khi tab đóng |
| IndexedDB | Bản ghi có cấu trúc, dữ liệu offline, hàng đợi đồng bộ | Bất đồng bộ, transaction, index và structured clone |
| Cache API | Request/Response cần cache, thường là app shell và tài nguyên tĩnh | Được quản lý tường minh bởi ứng dụng hoặc service worker |
| Origin Private File System (OPFS) | File lớn, dữ liệu nhị phân và thao tác file | Storage riêng theo origin, có API chuyên cho file |

Không có một cơ chế nào phù hợp cho mọi loại dữ liệu. Một ứng dụng offline có thể dùng IndexedDB cho bản ghi và Cache API cho JavaScript, CSS, font hoặc ảnh tĩnh. Cả hai vẫn thuộc nhóm dữ liệu lưu trữ của origin và có thể chịu quota, eviction hoặc thao tác xóa site data.

### 1.1 IndexedDB giải quyết vấn đề nào?

IndexedDB phù hợp khi ứng dụng cần:

- Lưu nhiều bản ghi thay vì một vài chuỗi cấu hình.
- Tìm bản ghi theo khóa hoặc index.
- Ghi nhiều thay đổi trong một transaction.
- Làm việc bất đồng bộ để tránh chặn giao diện.
- Lưu object, array, Date, Blob, ArrayBuffer và các giá trị hỗ trợ structured clone.
- Xây dựng tính năng offline hoặc đồng bộ dữ liệu khi mạng quay lại.

Ví dụ, ứng dụng ghi chú có thể lưu mỗi ghi chú thành một record với id, title, body và updatedAt. Ứng dụng có thể truy vấn ghi chú theo thời gian cập nhật thay vì đọc và parse toàn bộ một JSON lớn trong localStorage.

### 1.2 IndexedDB không phải máy chủ dữ liệu

IndexedDB lưu dữ liệu ở phía trình duyệt. Nó không thay thế cơ sở dữ liệu server có backup, kiểm soát truy cập tập trung và đồng bộ nhiều thiết bị.

Nếu dữ liệu quan trọng cần tồn tại qua nhiều thiết bị hoặc cần kiểm toán, server vẫn nên là nguồn dữ liệu có thẩm quyền. IndexedDB có thể là cache hoặc bản sao làm việc trên thiết bị.

## 2. Mô hình dữ liệu của IndexedDB

IndexedDB có một số khái niệm chính:

- **Database**: cơ sở dữ liệu được định danh bằng tên trong origin.
- **Object store**: nơi chứa các record, gần với một collection hoặc bảng.
- **Key**: giá trị định danh record.
- **Key path**: thuộc tính trong object được dùng làm key.
- **Index**: cấu trúc phụ để tìm record theo một thuộc tính.
- **Transaction**: phạm vi thao tác đọc/ghi có tính nguyên tử.
- **Cursor**: cách duyệt các record theo thứ tự khóa hoặc index.

Sơ đồ khái quát:

~~~text
Origin: https://app.example.test
        |
        +-- Database: notes-app (version 2)
              |
              +-- Object store: notes
              |      keyPath: id
              |      indexes:
              |        - by-updatedAt
              |        - by-category
              |
              +-- Object store: syncQueue
              |      keyPath: operationId
              |
              +-- Object store: settings
                     keyPath: key
~~~

Tên database và object store thuộc phạm vi origin. Một origin khác không thể tùy ý mở database của origin này theo SOP.

### 2.1 Database

Mở database bằng `indexedDB.open(name, version)`:

~~~js
const request = indexedDB.open("notes-app", 1);
~~~

Tham số version là số nguyên dương. Khi version lớn hơn version hiện tại hoặc database chưa tồn tại, trình duyệt phát sự kiện `upgradeneeded` để ứng dụng tạo hoặc thay đổi schema.

Nếu không truyền version, ứng dụng mở database hiện tại mà không yêu cầu nâng cấp schema.

### 2.2 Object store

Object store lưu record theo key. Có thể dùng key do ứng dụng cung cấp hoặc để IndexedDB tự tạo bằng `autoIncrement`.

Ví dụ dùng key path:

~~~js
const store = db.createObjectStore("notes", {
  keyPath: "id",
  autoIncrement: true
});
~~~

Với cấu hình này, ứng dụng có thể ghi object không có id và để IndexedDB sinh khóa tăng dần. Nếu dùng key path mà không bật autoIncrement, record phải có thuộc tính key hợp lệ trước khi ghi.

Không dùng autoIncrement như mã định danh bảo mật hoặc ID có thể đoán để cấp quyền truy cập tài nguyên phía server. Key chỉ là khóa lưu trữ cục bộ.

### 2.3 Index

Index cho phép tìm record theo một thuộc tính mà không phải quét toàn bộ object store:

~~~js
store.createIndex("by-updatedAt", "updatedAt");
store.createIndex("by-category", "category");
~~~

Có thể đặt index là unique:

~~~js
store.createIndex("by-email", "email", {
  unique: true
});
~~~

Nếu một record mới vi phạm unique index, thao tác ghi có thể thất bại với `ConstraintError`.

Index chiếm thêm dung lượng và cần được cập nhật khi record thay đổi. Chỉ tạo index cho truy vấn ứng dụng thực sự cần.

### 2.4 Key và structured clone

IndexedDB dùng thuật toán structured clone để sao chép dữ liệu vào và ra khỏi storage. Các kiểu thường dùng gồm string, number, Date, ArrayBuffer, Blob, typed arrays, arrays và object có cấu trúc phù hợp.

Không thể lưu mọi giá trị JavaScript. Ví dụ, function và DOM node không phải dữ liệu structured-cloneable thông thường. Hãy lưu dữ liệu thuần và tái tạo đối tượng runtime khi đọc.

Không lưu reference đến object rồi kỳ vọng thay đổi object trong bộ nhớ sẽ tự cập nhật record. Muốn lưu thay đổi, cần thực hiện thao tác `put()` hoặc `add()` trong transaction mới.

## 3. Tạo database và nâng cấp schema

Schema IndexedDB được tạo hoặc thay đổi trong versionchange transaction, thường thông qua sự kiện `upgradeneeded`.

Ví dụ tạo database và object store:

~~~js
function openNotesDatabase() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open("notes-app", 1);

    request.onupgradeneeded = event => {
      const db = event.target.result;

      if (!db.objectStoreNames.contains("notes")) {
        const notes = db.createObjectStore("notes", {
          keyPath: "id",
          autoIncrement: true
        });

        notes.createIndex("by-updatedAt", "updatedAt");
        notes.createIndex("by-category", "category");
      }
    };

    request.onsuccess = () => {
      const db = request.result;

      db.onversionchange = () => {
        db.close();
      };

      resolve(db);
    };

    request.onerror = () => {
      reject(request.error);
    };

    request.onblocked = () => {
      console.warn("Database upgrade is blocked by another connection");
    };
  });
}
~~~

`openNotesDatabase()` trả về Promise để phần còn lại của ứng dụng có thể dùng await.

### 3.1 Vì sao cần version?

Giả sử phiên bản đầu chỉ có object store `notes`. Sau đó ứng dụng cần thêm `syncQueue`. Có thể tăng version database và tạo store mới:

~~~js
const request = indexedDB.open("notes-app", 2);

request.onupgradeneeded = event => {
  const db = event.target.result;

  if (!db.objectStoreNames.contains("syncQueue")) {
    db.createObjectStore("syncQueue", {
      keyPath: "operationId"
    });
  }
};
~~~

Việc thay đổi schema diễn ra trong versionchange transaction. Đây là nơi tạo hoặc xóa object store, tạo index và thực hiện migration dữ liệu cần thiết.

Không thực hiện network request dài trong `upgradeneeded`. Upgrade transaction phải hoàn thành trong vòng đời transaction của IndexedDB. Nếu migration cần dữ liệu từ server, hãy tải dữ liệu trước rồi mở transaction để ghi.

### 3.2 Blocked và versionchange

Nếu tab A đang giữ kết nối database version 1, tab B yêu cầu mở version 2, trình duyệt có thể chờ tab A đóng kết nối. Tab B phát sự kiện `blocked`.

Kết nối cũ nhận `versionchange`. Ứng dụng nên đóng kết nối để tab khác có thể nâng cấp:

~~~js
db.onversionchange = () => {
  db.close();
  notifyUserToReload();
};
~~~

`notifyUserToReload()` là hàm giao diện do ứng dụng định nghĩa. Nếu không đóng kết nối cũ, quá trình nâng cấp có thể bị treo và các tab khác không dùng được schema mới.

Đây là lý do ứng dụng nhiều tab cần quản lý connection lifecycle cẩn thận.

## 4. Transaction: đơn vị đọc và ghi

Mọi thao tác IndexedDB diễn ra trong transaction. Transaction xác định object store được phép truy cập và mode của thao tác.

Hai mode phổ biến:

| Mode | Mục đích | Ví dụ |
|---|---|---|
| `readonly` | Chỉ đọc record | Tìm ghi chú, liệt kê bản ghi |
| `readwrite` | Đọc và thay đổi record | Thêm, cập nhật hoặc xóa ghi chú |

Một transaction có tính nguyên tử: nếu transaction bị abort, các thay đổi trong transaction không được commit một phần.

### 4.1 Ghi record

Ví dụ thêm hoặc thay thế ghi chú theo key:

~~~js
function saveNote(db, note) {
  return new Promise((resolve, reject) => {
    const tx = db.transaction("notes", "readwrite");
    const store = tx.objectStore("notes");

    store.put({
      ...note,
      updatedAt: Date.now()
    });

    tx.oncomplete = () => resolve();
    tx.onabort = () => {
      reject(tx.error || new Error("Transaction aborted"));
    };
  });
}
~~~

`put()` thêm record mới hoặc thay thế record có cùng key. `add()` chỉ thêm và thất bại nếu key đã tồn tại.

Đợi transaction hoàn tất thay vì chỉ đợi request `put()` thành công. Một request riêng lẻ có thể thành công nhưng transaction sau đó vẫn bị abort bởi lỗi khác.

### 4.2 Đọc record

~~~js
function readNote(db, id) {
  return new Promise((resolve, reject) => {
    const tx = db.transaction("notes", "readonly");
    const request = tx.objectStore("notes").get(id);

    request.onsuccess = () => {
      resolve(request.result);
    };

    request.onerror = () => {
      reject(request.error);
    };
  });
}
~~~

Nếu không có record với key đó, `result` thường là `undefined`.

### 4.3 Xóa record

~~~js
function deleteNote(db, id) {
  return new Promise((resolve, reject) => {
    const tx = db.transaction("notes", "readwrite");

    tx.objectStore("notes").delete(id);

    tx.oncomplete = () => resolve();
    tx.onabort = () => {
      reject(tx.error || new Error("Delete transaction aborted"));
    };
  });
}
~~~

Xóa một record không xóa index hoặc các record liên quan trong store khác. Nếu ứng dụng cần xóa dữ liệu liên quan, hãy thực hiện trong một transaction bao gồm tất cả object store cần thiết.

### 4.4 Không chờ network bên trong transaction

Transaction IndexedDB có vòng đời ngắn. Khi không còn request nào đang chờ và event loop trả quyền điều khiển, transaction có thể tự commit. Vì vậy, không viết kiểu:

~~~js
const tx = db.transaction("notes", "readwrite");
const response = await fetch("/api/notes/42");
const note = await response.json();
tx.objectStore("notes").put(note);
~~~

Sau khi `await fetch()` hoàn tất, transaction có thể đã inactive hoặc committed. Lệnh `put()` sau đó có thể ném `TransactionInactiveError`.

Hãy lấy dữ liệu mạng trước, sau đó mở transaction mới:

~~~js
const response = await fetch("/api/notes/42");
if (!response.ok) {
  throw new Error("Cannot load note");
}

const note = await response.json();
await saveNote(db, note);
~~~

Giữ transaction ngắn và chỉ thực hiện các thao tác IndexedDB bên trong vòng đời của nó.

### 4.5 Gộp nhiều thao tác trong một transaction

Nếu cần cập nhật ghi chú và xóa một mục khỏi hàng đợi đồng bộ, hãy dùng một transaction gồm cả hai store:

~~~js
const tx = db.transaction(
  ["notes", "syncQueue"],
  "readwrite"
);

tx.objectStore("notes").put(updatedNote);
tx.objectStore("syncQueue").delete(operationId);
~~~

Hai thao tác được commit cùng nhau. Nếu transaction abort, cả hai thay đổi đều bị hủy.

## 5. Truy vấn bằng key, index và cursor

### 5.1 get và getAll

`get(key)` đọc một record theo khóa. `getAll()` trả về nhiều record phù hợp, nhưng không nên dùng để tải toàn bộ database lớn vào RAM.

~~~js
const tx = db.transaction("notes", "readonly");
const request = tx.objectStore("notes").getAll();
~~~

Có thể truyền `IDBKeyRange` để giới hạn khoảng key:

~~~js
const range = IDBKeyRange.bound(10, 100);
const request = store.getAll(range);
~~~

Hãy giới hạn số record khi dữ liệu lớn.

### 5.2 Truy vấn qua index

~~~js
const tx = db.transaction("notes", "readonly");
const index = tx.objectStore("notes").index("by-category");
const request = index.getAll("work");
~~~

Index hữu ích cho truy vấn theo category, updatedAt hoặc các thuộc tính có tính chọn lọc.

### 5.3 Cursor

Cursor cho phép duyệt từng record theo thứ tự key hoặc index:

~~~js
function listNotesByDate(db) {
  return new Promise((resolve, reject) => {
    const tx = db.transaction("notes", "readonly");
    const index = tx.objectStore("notes").index("by-updatedAt");
    const results = [];

    const request = index.openCursor(null, "prev");

    request.onsuccess = event => {
      const cursor = event.target.result;

      if (!cursor) {
        resolve(results);
        return;
      }

      results.push(cursor.value);
      cursor.continue();
    };

    request.onerror = () => reject(request.error);
  });
}
~~~

Cursor phù hợp khi cần duyệt dữ liệu lớn theo từng record hoặc xử lý theo batch. Tuy nhiên, không giữ một transaction mở quá lâu để làm công việc không liên quan đến database.

## 6. Xử lý lỗi và tính toàn vẹn dữ liệu

IndexedDB có nhiều loại lỗi khác nhau. Ứng dụng cần xử lý ở cấp request và transaction.

| Lỗi hoặc sự kiện | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `QuotaExceededError` | Không đủ quota để ghi dữ liệu | Dọn dữ liệu cache có thể tái tạo, giảm dữ liệu và thông báo cho người dùng |
| `ConstraintError` | Trùng key hoặc vi phạm unique index | Kiểm tra dữ liệu và chính sách tạo record |
| `DataError` | Key hoặc dữ liệu không hợp lệ | Validate trước khi ghi |
| `TransactionInactiveError` | Dùng transaction sau khi nó hết vòng đời | Mở transaction mới và tránh await network bên trong |
| `AbortError` | Transaction bị hủy | Xem nguyên nhân trước đó và retry có giới hạn nếu phù hợp |
| `VersionError` | Yêu cầu mở version thấp hơn database hiện có | Đồng bộ version ứng dụng và schema |
| `blocked` | Kết nối cũ chưa đóng khi cần upgrade | Xử lý versionchange và yêu cầu tab cũ đóng connection |

Không bắt mọi lỗi rồi bỏ qua. Nếu ghi dữ liệu thất bại mà giao diện vẫn báo “đã lưu”, người dùng có thể mất nội dung khi reload.

### 6.1 Kiểm tra dữ liệu trước khi lưu

IndexedDB không thay thế validation nghiệp vụ. Hãy kiểm tra:

- Kiểu dữ liệu và giới hạn kích thước.
- Trường bắt buộc.
- Giá trị enum hợp lệ.
- Quan hệ giữa các record.
- Phiên bản schema và format dữ liệu.
- Quyền sở hữu record theo user đang đăng nhập.

Dữ liệu đọc từ IndexedDB cũng phải được xem là dữ liệu không tin cậy. Người dùng có thể chỉnh sửa site data bằng DevTools hoặc extension; dữ liệu có thể cũ, sai hoặc được tạo bởi phiên bản ứng dụng khác.

## 7. Quota: trình duyệt giới hạn dung lượng thế nào?

Browser storage không có dung lượng vô hạn. Trình duyệt quản lý quota theo origin hoặc storage bucket tùy kiến trúc và chính sách của trình duyệt.

Quota phụ thuộc vào:

- Trình duyệt và phiên bản.
- Hệ điều hành và dung lượng thiết bị.
- Chế độ duyệt thông thường hay riêng tư.
- Tổng dung lượng đã dùng bởi origin hoặc storage group.
- Chính sách quản lý dung lượng của trình duyệt.
- Dung lượng còn lại trên thiết bị.

Không hardcode một con số quota chung cho mọi người dùng. Các con số trong tài liệu của một trình duyệt có thể thay đổi theo phiên bản, thiết bị và loại storage.

### 7.1 Ước lượng usage và quota

Storage Manager API cung cấp `navigator.storage.estimate()`:

~~~js
async function inspectStorage() {
  if (!navigator.storage?.estimate) {
    return null;
  }

  const estimate = await navigator.storage.estimate();

  return {
    usage: estimate.usage,
    quota: estimate.quota,
    usageDetails: estimate.usageDetails
  };
}

inspectStorage().then(result => {
  console.log(result);
});
~~~

`usage` và `quota` là giá trị ước lượng theo byte. `usageDetails` có thể cung cấp phân loại như IndexedDB hoặc Cache Storage ở một số trình duyệt, nhưng không phải trình duyệt nào cũng trả đầy đủ.

Không hiển thị con số estimate như cam kết rằng ứng dụng có thể ghi thêm đúng `quota - usage` byte. Đây là số liệu ước lượng và có thể thay đổi ngay sau khi query.

### 7.2 Xử lý QuotaExceededError

Một thao tác ghi có thể thất bại vì vượt quota:

~~~js
try {
  await saveLargeDataset(db, dataset);
} catch (error) {
  if (error?.name === "QuotaExceededError") {
    await removeRebuildableCache();
    showStorageLimitMessage();
  } else {
    throw error;
  }
}
~~~

`saveLargeDataset`, `removeRebuildableCache` và `showStorageLimitMessage` là các hàm ứng dụng tự định nghĩa.

Khi quota bị vượt:

1. Dừng retry vô hạn.
2. Xác định dữ liệu nào có thể tái tạo từ server.
3. Xóa cache cũ hoặc dữ liệu hết hạn theo chính sách.
4. Giảm kích thước dữ liệu hoặc chỉ lưu phần cần thiết.
5. Thử lại một lần nếu có lý do rõ ràng.
6. Nếu vẫn thất bại, báo người dùng và bảo toàn dữ liệu chưa đồng bộ ở nơi an toàn nhất có thể.

Không xóa dữ liệu người dùng chưa đồng bộ chỉ để giải phóng dung lượng mà không có chính sách phục hồi.

## 8. Persistent storage và eviction

### 8.1 Best-effort storage

Phần lớn browser storage mặc định là best-effort. Trình duyệt cố giữ dữ liệu, nhưng có thể xóa dữ liệu origin khi thiếu dung lượng hoặc theo chính sách quản lý storage.

Eviction thường ảnh hưởng đến dữ liệu của origin như IndexedDB, Cache API và các cơ chế lưu trữ liên quan. Chi tiết thứ tự và phạm vi xóa khác nhau giữa các trình duyệt.

Điều này có nghĩa:

- IndexedDB không phải backup.
- Cache API không phải nơi lưu dữ liệu duy nhất.
- Ứng dụng offline cần có chiến lược đồng bộ và khôi phục.
- Dữ liệu chưa đồng bộ cần được ưu tiên bảo vệ.
- Không hứa với người dùng rằng dữ liệu sẽ tồn tại mãi trên thiết bị.

### 8.2 Yêu cầu persistent storage

Ứng dụng có thể hỏi trình duyệt có cấp persistent storage cho origin hay không:

~~~js
async function requestPersistentStorage() {
  if (!navigator.storage?.persist) {
    return false;
  }

  return navigator.storage.persist();
}
~~~

Kết quả là boolean. Trình duyệt có quyền quyết định có cấp hay không, dựa trên heuristic và chính sách riêng. Một số trình duyệt có thể tự cấp hoặc từ chối mà không hiện prompt rõ ràng.

Có thể kiểm tra trạng thái hiện tại:

~~~js
const isPersistent = await navigator.storage.persisted();
console.log({ isPersistent });
~~~

Persistent storage giúp giảm nguy cơ trình duyệt tự động eviction dữ liệu origin trong các điều kiện hỗ trợ. Nó không ngăn người dùng chủ động xóa site data, không bảo vệ khỏi hỏng thiết bị và không thay thế backup server.

Chỉ yêu cầu persistent storage khi ứng dụng có lý do rõ ràng, ví dụ dữ liệu offline do người dùng tạo và cần được giữ để đồng bộ sau. Không yêu cầu chỉ để tăng quota cho cache tài nguyên có thể tải lại.

### 8.3 Eviction không giống xóa cache của ứng dụng

Có hai hoạt động khác nhau:

- **Application cleanup**: ứng dụng chủ động xóa cache cũ, bản ghi hết hạn hoặc dữ liệu có thể tái tạo.
- **Browser eviction**: trình duyệt thu hồi dữ liệu storage theo chính sách quota và áp lực dung lượng.

Ứng dụng có thể kiểm soát cleanup của chính mình. Nó không kiểm soát hoàn toàn khi nào browser eviction xảy ra.

### 8.4 Không giả định IndexedDB sẽ tồn tại sau khi người dùng xóa site data

Người dùng có thể xóa toàn bộ dữ liệu của origin trong cài đặt trình duyệt. Hành động này có thể xóa IndexedDB, Cache Storage, localStorage, cookie và dữ liệu liên quan.

Nếu ứng dụng cần giữ dữ liệu qua nhiều thiết bị hoặc sau khi người dùng reset trình duyệt, cần đồng bộ lên server và có cơ chế phục hồi.

## 9. Cache API: lưu Request và Response

Cache API là một phần của Cache Storage API. Nó cho phép ứng dụng lưu các cặp Request/Response để tái sử dụng, thường thông qua service worker.

Ví dụ cache app shell:

~~~js
const CACHE_NAME = "app-shell-v3";
const APP_ASSETS = [
  "/",
  "/index.html",
  "/assets/app.css",
  "/assets/app.js"
];

async function installAppCache() {
  const cache = await caches.open(CACHE_NAME);
  await cache.addAll(APP_ASSETS);
}
~~~

Service worker có thể gọi hàm này trong install event:

~~~js
self.addEventListener("install", event => {
  event.waitUntil(installAppCache());
});
~~~

Cache API lưu Response body và metadata theo request key. Ứng dụng có thể dùng `cache.match()`, `cache.put()`, `cache.delete()` và `caches.delete()` để quản lý cache.

### 9.1 Cache API khác IndexedDB

| Đặc điểm | IndexedDB | Cache API |
|---|---|---|
| Mô hình | Record có key và object store | Request/Response |
| Truy vấn | Key, index, range, cursor | Match theo request và CacheQueryOptions |
| Giao dịch | Có transaction | Không có transaction đa mục như IndexedDB |
| Phù hợp | Dữ liệu ứng dụng có cấu trúc | Tài nguyên HTTP cần tái sử dụng |
| Quản lý hết hạn | Ứng dụng tự thiết kế | Ứng dụng tự thiết kế |
| Quota | Thuộc browser storage | Cùng hệ sinh thái quota của origin |

Cache API không phải HTTP cache của trình duyệt. HTTP cache được trình duyệt quản lý theo HTTP caching semantics; Cache API là storage mà ứng dụng thao tác tường minh.

Một điểm quan trọng: Cache API không tự tuân thủ các header HTTP caching như `Cache-Control: no-store` theo cách HTTP cache làm. Nếu code gọi `cache.put()` để lưu response, ứng dụng phải tự chịu trách nhiệm quyết định có nên lưu hay không, thời hạn và cách xóa.

### 9.2 Cache API không tự hết hạn theo tuổi

Cache API không cung cấp TTL chung cho mỗi entry. Ứng dụng phải tự đặt chiến lược versioning hoặc metadata hết hạn.

Ví dụ xóa cache version cũ khi service worker activate:

~~~js
const CURRENT_CACHE = "app-shell-v3";

self.addEventListener("activate", event => {
  event.waitUntil(
    caches.keys().then(names =>
      Promise.all(
        names
          .filter(name =>
            name.startsWith("app-shell-") &&
            name !== CURRENT_CACHE
          )
          .map(name => caches.delete(name))
      )
    )
  );
});
~~~

Chỉ xóa cache do ứng dụng sở hữu, dùng prefix riêng. Không xóa toàn bộ Cache Storage nếu origin có thể chứa cache của module hoặc ứng dụng khác.

### 9.3 Không cache dữ liệu nhạy cảm tùy tiện

Tránh lưu response chứa:

- Trang tài khoản cá nhân.
- Dữ liệu hồ sơ, thông tin định danh.
- Kết quả tài chính hoặc thanh toán.
- Nội dung y tế hoặc dữ liệu nhạy cảm.
- Response chứa token hoặc session secret.
- Dữ liệu phụ thuộc người dùng đang đăng nhập nếu chưa có chính sách cache rõ ràng.

Cache API là persistent browser storage. Một response đã cache có thể còn tồn tại sau logout hoặc sau khi session hết hạn nếu ứng dụng không xóa nó. Nếu cache response cá nhân là yêu cầu bắt buộc, phải thiết kế key theo account/session, thời hạn, invalidation, logout cleanup và xử lý account switch.

Không dựa vào `Cache-Control: no-store` để ngăn code ứng dụng tự gọi Cache API lưu response. Hãy kiểm tra logic `cache.put()` và `cache.add()`.

## 10. Bảo vệ dữ liệu nhạy cảm trong IndexedDB và Cache Storage

IndexedDB và Cache API thuộc storage của origin. Same-Origin Policy ngăn origin khác đọc dữ liệu trực tiếp, nhưng mọi JavaScript có quyền chạy trong origin đều có thể truy cập storage mà ứng dụng được phép dùng.

Đây là điểm bảo mật quan trọng: IndexedDB không phải vault và không phải ranh giới chống XSS.

### 10.1 XSS có thể đọc dữ liệu lưu cục bộ

Nếu kẻ tấn công thực thi JavaScript trong origin của ứng dụng, mã đó có thể:

- Mở database IndexedDB của ứng dụng.
- Đọc record và index.
- Truy cập Cache Storage.
- Đọc dữ liệu đã cache trong cùng origin.
- Gửi dữ liệu ra ngoài nếu CSP và các kiểm soát khác không chặn.

Vì vậy, không lưu dữ liệu bí mật chỉ vì nó nằm trong IndexedDB thay vì localStorage. Cả hai đều có thể bị mã same-origin đọc nếu XSS xảy ra.

### 10.2 Không lưu access token hoặc refresh token dài hạn trong IndexedDB

Nếu token được lưu trong IndexedDB, script XSS có thể đọc và lấy token. Hãy ưu tiên kiến trúc xác thực dùng cookie session có cấu hình `HttpOnly`, `Secure`, `SameSite` phù hợp, kết hợp CSRF protection và kiểm soát phía server.

Không phải mọi hệ thống đều dùng cookie session, nhưng nếu lưu token ở phía client là bắt buộc, cần đánh giá thời hạn ngắn, scope hẹp, rotation, revocation và tác động của XSS. Mã hóa token bằng khóa mà JavaScript cùng origin có thể truy cập không giải quyết được kịch bản XSS đang chạy trong cùng ngữ cảnh.

### 10.3 Mã hóa dữ liệu tại client có giới hạn

Web Crypto API có thể mã hóa dữ liệu trước khi lưu. Điều này có ích trong một số mô hình bảo vệ dữ liệu khi thiết bị hoặc bản sao storage bị truy cập ngoài ứng dụng, nhưng cần quản lý khóa đúng cách.

Nếu khóa giải mã được lưu trong IndexedDB hoặc có thể lấy trực tiếp từ JavaScript runtime, XSS có thể lấy khóa hoặc gọi API giải mã. Không tuyên bố rằng mã hóa client-side tự động bảo vệ dữ liệu khỏi XSS.

Ngay cả khi dùng `CryptoKey` với `extractable: false`, thuộc tính này chỉ ngăn xuất material của khóa qua các API export. Nếu mã độc cùng origin có thể lấy được đối tượng khóa hoặc gọi luồng mã hóa/giải mã thay ứng dụng, nó vẫn có thể sử dụng khóa mà không cần đọc được byte khóa. Vì vậy, khóa không thể export không tự tạo ra ranh giới chống XSS.

Đối với dữ liệu nhạy cảm, hãy xác định threat model:

- Bảo vệ khỏi người dùng khác trên cùng thiết bị?
- Bảo vệ bản sao dữ liệu trên đĩa?
- Bảo vệ khi thiết bị bị mất?
- Bảo vệ khỏi mã độc cùng origin?
- Bảo vệ dữ liệu khi người dùng đăng xuất?

Mỗi mục tiêu cần một giải pháp khác nhau. OS disk encryption, browser profile protection, server-side authorization và chống XSS có vai trò khác nhau.

### 10.4 Data minimization

Chỉ lưu những trường cần cho tính năng offline hoặc trải nghiệm người dùng. Ví dụ:

- Lưu bản nháp cần đồng bộ thay vì toàn bộ hồ sơ tài khoản.
- Lưu id và metadata cần thiết thay vì token xác thực.
- Không lưu dữ liệu nhạy cảm lâu hơn thời gian cần thiết.
- Không ghi dữ liệu nhạy cảm vào console log.
- Tránh cache response cá nhân không có thời hạn rõ ràng.

Dữ liệu không được lưu thì không thể bị rò rỉ từ storage đó.

## 11. Logout và chuyển đổi tài khoản

Ứng dụng hỗ trợ nhiều tài khoản trên cùng browser profile phải có chính sách riêng cho dữ liệu local.

Nếu người dùng đăng xuất, cần quyết định:

- Xóa dữ liệu nhạy cảm của account hiện tại?
- Giữ bản nháp chưa đồng bộ và hỏi người dùng?
- Xóa cache response có dữ liệu cá nhân?
- Giữ app shell và tài nguyên tĩnh?
- Khi tài khoản khác đăng nhập, có thể nhìn thấy dữ liệu cũ không?

### 11.1 Namespace dữ liệu theo account

Có thể dùng key hoặc field accountId để phân vùng dữ liệu theo người dùng. Tuy nhiên, đây chỉ là tổ chức dữ liệu, không phải authorization boundary. Server vẫn phải xác minh quyền khi đồng bộ hoặc truy xuất dữ liệu.

Không tin accountId lấy từ IndexedDB như bằng chứng rằng người dùng được phép đọc record đó.

### 11.2 Dọn dữ liệu khi logout

Ứng dụng có thể xóa record nhạy cảm trong IndexedDB bằng transaction và xóa cache riêng của tài khoản:

~~~js
async function clearPrivateClientData(db, privateCacheName) {
  await new Promise((resolve, reject) => {
    const tx = db.transaction(
      ["privateRecords", "syncQueue"],
      "readwrite"
    );

    tx.objectStore("privateRecords").clear();
    tx.objectStore("syncQueue").clear();

    tx.oncomplete = resolve;
    tx.onabort = () => {
      reject(tx.error || new Error("Logout cleanup aborted"));
    };
  });

  await caches.delete(privateCacheName);
}
~~~

Đây là ví dụ minh họa. Chỉ xóa các store và cache mà ứng dụng sở hữu. Nếu cần giữ thao tác offline chưa đồng bộ, không xóa queue trước khi có quyết định nghiệp vụ hoặc cơ chế bảo toàn dữ liệu.

### 11.3 Xóa database

Có thể yêu cầu xóa database bằng `indexedDB.deleteDatabase(name)`:

~~~js
function deleteNotesDatabase() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.deleteDatabase("notes-app");

    request.onsuccess = () => resolve();
    request.onerror = () => reject(request.error);
    request.onblocked = () => {
      console.warn("Close other tabs before deleting the database");
    };
  });
}
~~~

Các tab khác đang mở database có thể làm thao tác xóa bị blocked. Hãy đóng connection khi nhận `versionchange` và phối hợp nhiều tab.

Xóa record hoặc database không phải bảo đảm secure erase vật lý trên SSD hay thiết bị. Trình duyệt quản lý cách lưu trữ nội bộ; ứng dụng web không kiểm soát được việc xóa vật lý ở tầng phần cứng.

## 12. Offline-first và đồng bộ dữ liệu

IndexedDB thường được dùng làm local working copy cho ứng dụng offline.

Một mô hình đơn giản:

~~~text
Người dùng chỉnh sửa dữ liệu
        |
        v
Ghi vào IndexedDB
        |
        v
Đưa operation vào syncQueue
        |
        v
Có mạng?
   |          |
  Chưa        Có
   |          |
Giữ queue     Gửi request đến server
              |
              v
        Server xác thực và lưu
              |
              v
        Xóa operation đã đồng bộ
~~~

### 12.1 Ghi local trước, đồng bộ sau

Ứng dụng có thể lưu thay đổi vào IndexedDB để giao diện phản hồi nhanh. Sau đó, worker hoặc ứng dụng đồng bộ queue khi có mạng.

Mỗi operation nên có idempotency key hoặc ID duy nhất để server xử lý retry mà không tạo bản ghi trùng. Không tin dữ liệu local là đúng chỉ vì transaction đã commit.

### 12.2 Xử lý conflict

Nếu cùng một record được sửa trên hai thiết bị, ứng dụng cần chính sách conflict:

- Last-write-wins theo timestamp server.
- Version hoặc revision number.
- Merge theo field.
- Giữ bản sao conflict để người dùng chọn.
- Quy tắc nghiệp vụ riêng.

Timestamp từ client có thể sai hoặc bị chỉnh. Với dữ liệu quan trọng, server nên quyết định thứ tự hoặc kiểm tra version.

### 12.3 Dữ liệu chưa đồng bộ và eviction

Nếu browser eviction xóa IndexedDB trước khi queue được đồng bộ, người dùng có thể mất thay đổi local. Vì vậy:

- Đồng bộ sớm khi có mạng.
- Hiển thị trạng thái “chưa đồng bộ”.
- Có retry có giới hạn và backoff.
- Cân nhắc persistent storage khi dữ liệu offline do người dùng tạo có giá trị cao.
- Không hứa dữ liệu offline được giữ mãi.
- Với dữ liệu quan trọng, cần cơ chế backup hoặc export.

## 13. Quản lý Cache API an toàn trong service worker

Service worker thường dùng Cache API để phục vụ app shell và tài nguyên có thể tái tạo.

Ví dụ chiến lược cache-first cho tài nguyên tĩnh:

~~~js
const STATIC_CACHE = "static-v4";

self.addEventListener("fetch", event => {
  const request = event.request;
  const url = new URL(request.url);

  if (
    request.method !== "GET" ||
    url.origin !== self.location.origin ||
    !url.pathname.startsWith("/assets/")
  ) {
    return;
  }

  event.respondWith((async () => {
    const cache = await caches.open(STATIC_CACHE);
    const cached = await cache.match(request);

    if (cached) {
      return cached;
    }

    const response = await fetch(request);

    if (response.ok && response.type === "basic") {
      await cache.put(request, response.clone());
    }

    return response;
  })());
});
~~~

Ví dụ chỉ cache GET cùng origin trong `/assets/`. Đây là một allowlist đơn giản cho tài nguyên tĩnh; ứng dụng thật cần cân nhắc query string, content version, response headers, lỗi mạng và chiến lược cập nhật.

Không dùng cùng chiến lược cache-first cho endpoint tài khoản hoặc API chứa dữ liệu cá nhân.

### 13.1 Chọn chiến lược theo loại dữ liệu

| Loại request | Chiến lược gợi ý | Lưu ý |
|---|---|---|
| App shell, CSS, JS có version | Cache-first hoặc precache | Có thể tái tạo từ server |
| Ảnh tĩnh, font | Cache-first với version/cleanup | Giới hạn dung lượng |
| API công khai, ít thay đổi | Stale-while-revalidate hoặc network-first | Đặt thời hạn và invalidation |
| API tài khoản cá nhân | Thường network-first hoặc không cache | Tránh dữ liệu cũ lộ qua account switch |
| Token, session secret | Không lưu trong Cache API | Dùng cơ chế xác thực phù hợp |
| Dữ liệu offline do người dùng tạo | IndexedDB + sync queue | Có backup và chính sách eviction |

### 13.2 Response opaque

Request no-CORS cross-origin có thể trả opaque response. Ứng dụng không thể đọc status, headers hoặc body của opaque response theo cách thông thường. Việc cache opaque response có thể làm tăng dung lượng mà không cho phép ứng dụng kiểm tra nội dung.

Chỉ cache opaque response khi nguồn và use case đã được đánh giá. Ưu tiên CORS response có thể kiểm tra khi cần xác nhận status, content type và các thuộc tính response.

## 14. Những nhầm lẫn thường gặp

### 14.1 Nghĩ IndexedDB được mã hóa vì nằm trong trình duyệt

IndexedDB không cung cấp cam kết mã hóa ứng dụng ở cấp API. Bảo vệ dữ liệu phụ thuộc hệ điều hành, profile, thiết bị và threat model.

### 14.2 Nghĩ dữ liệu IndexedDB không thể bị XSS đọc

JavaScript chạy cùng origin có thể mở database và đọc record. Hãy giảm dữ liệu nhạy cảm và chống XSS bằng CSP, Trusted Types, output encoding và API DOM an toàn.

### 14.3 Nghĩ transaction có thể chờ tùy ý

Transaction có vòng đời ngắn. Chờ network hoặc tác vụ lâu có thể khiến transaction inactive hoặc tự commit. Tách network và database work thành các bước riêng.

### 14.4 Nghĩ quota là một con số cố định

Quota thay đổi theo trình duyệt, thiết bị và dung lượng hiện có. Dùng Storage Manager API để ước lượng và xử lý lỗi ghi.

### 14.5 Nghĩ persist() ngăn người dùng xóa dữ liệu

Persistent storage chỉ ảnh hưởng đến cơ chế tự động eviction trong phạm vi trình duyệt hỗ trợ. Người dùng vẫn có thể xóa site data và thiết bị vẫn có thể hỏng.

### 14.6 Nghĩ Cache API tự tuân thủ Cache-Control

Cache API là storage tường minh của ứng dụng và không tự áp dụng HTTP caching headers như HTTP cache. Code phải quyết định có lưu response hay không.

### 14.7 Nghĩ logout tự xóa Cache Storage

Logout không tự động xóa IndexedDB hoặc Cache API. Ứng dụng phải dọn dữ liệu thuộc quyền sở hữu của mình theo chính sách tài khoản.

### 14.8 Nghĩ xóa database là secure erase

API xóa database không bảo đảm ghi đè vật lý các block lưu trữ. Không hứa xóa an toàn ở tầng phần cứng từ JavaScript.

## 15. Bài thực hành

Thực hiện trên website HTTPS hoặc localhost do bạn kiểm soát. Dùng dữ liệu giả lập, không lưu token hoặc thông tin cá nhân thật.

### Bài 1: Tạo database và object store

Tạo database `notes-lab`, object store `notes` với keyPath `id`, autoIncrement và index `by-updatedAt`. Thêm ba record, đọc theo key và duyệt theo index.

### Bài 2: Nâng cấp schema

Mở database version 2 và thêm object store `syncQueue`. Mở hai tab, giữ connection ở tab đầu rồi thử upgrade ở tab thứ hai. Quan sát `blocked` và `versionchange`; đóng connection cũ để hoàn tất.

### Bài 3: Transaction và rollback

Tạo transaction ghi vào hai object store. Cố ý tạo lỗi unique constraint trong một request. Quan sát transaction abort và xác nhận các thay đổi trước đó không được commit một phần.

### Bài 4: Quota và persistent storage

Gọi `navigator.storage.estimate()` để ghi lại usage/quota. Gọi `navigator.storage.persist()` và `navigator.storage.persisted()`. So sánh kết quả trên profile thường và profile riêng tư nếu trình duyệt hỗ trợ.

Không tạo dữ liệu lớn vô hạn để ép đầy đĩa. Dùng lượng dữ liệu lab nhỏ và dọn sau khi kiểm tra.

### Bài 5: Cache API và version cleanup

Tạo hai cache version `static-v1` và `static-v2`. Lưu một số tài nguyên giả lập, sau đó viết activate handler chỉ xóa cache cũ có prefix do ứng dụng sở hữu.

### Bài 6: Kiểm tra dữ liệu nhạy cảm

Lưu một record giả lập có access token giả và quan sát khả năng đọc từ Console cùng origin. Xóa record, sau đó thiết kế lại schema chỉ lưu dữ liệu không nhạy cảm cần cho offline. Giải thích vì sao mã hóa bằng khóa có sẵn trong JavaScript không bảo vệ được trước XSS.

### Bài 7: Logout và account switch

Tạo hai account giả lập. Cache một response cá nhân cho account A, sau đó logout và đăng nhập account B. Xác nhận dữ liệu của A không xuất hiện trong giao diện hoặc cache lookup của B. Giữ app shell tĩnh nếu cần.

## 16. Checklist review IndexedDB và browser storage

- [ ] Đã chọn IndexedDB cho dữ liệu có cấu trúc và Cache API cho Request/Response phù hợp.
- [ ] Schema có version và migration rõ ràng.
- [ ] Object store và index chỉ được tạo khi cần truy vấn.
- [ ] Transaction ngắn, không chờ network bên trong transaction.
- [ ] Đợi transaction complete trước khi báo lưu thành công.
- [ ] Xử lý blocked, versionchange, QuotaExceededError và abort.
- [ ] Không hardcode quota hoặc hứa dữ liệu tồn tại vĩnh viễn.
- [ ] Có dùng navigator.storage.estimate() khi cần theo dõi dung lượng.
- [ ] Chỉ yêu cầu navigator.storage.persist() khi có lý do rõ ràng.
- [ ] Có chiến lược eviction, cleanup và đồng bộ dữ liệu chưa gửi.
- [ ] Cache API chỉ lưu nguồn và response đã được allowlist.
- [ ] Có versioning và cleanup cache cũ.
- [ ] Không dựa vào Cache-Control để ngăn code Cache API lưu response.
- [ ] Không lưu access token, refresh token hoặc secret dài hạn trong IndexedDB/Cache Storage.
- [ ] Dữ liệu local được xem là có thể bị đọc bởi XSS cùng origin.
- [ ] Có data minimization, retention và cleanup khi logout/account switch.
- [ ] Server vẫn xác thực, phân quyền và là nguồn dữ liệu có thẩm quyền.
- [ ] Có backup hoặc export cho dữ liệu người dùng không thể tái tạo.
- [ ] Đã kiểm thử trên các trình duyệt và chế độ duyệt mục tiêu.

## 17. Câu hỏi tự kiểm tra

**1. IndexedDB phù hợp với loại dữ liệu nào?**

Dữ liệu có cấu trúc, nhiều record, cần truy vấn theo key/index và cần thao tác bất đồng bộ bằng transaction.

**2. Object store là gì?**

Là nơi lưu các record trong database, mỗi record được định danh bằng key.

**3. Versionchange transaction dùng để làm gì?**

Dùng khi tạo database hoặc nâng cấp schema, ví dụ thêm object store hay index.

**4. Vì sao không nên await fetch bên trong transaction?**

Vì transaction có vòng đời ngắn và có thể inactive hoặc commit khi không còn request IndexedDB đang chờ.

**5. get() và put() khác nhau thế nào?**

`get()` đọc record theo key; `put()` thêm hoặc thay thế record có key tương ứng.

**6. navigator.storage.estimate() cung cấp gì?**

Cung cấp ước lượng usage và quota hiện tại của storage origin; không phải cam kết dung lượng còn trống.

**7. persist() có ngăn người dùng xóa dữ liệu không?**

Không. Nó chỉ yêu cầu chế độ persistent storage để giảm nguy cơ browser eviction tự động trong phạm vi trình duyệt hỗ trợ.

**8. Cache API khác HTTP cache thế nào?**

Cache API là storage tường minh mà ứng dụng quản lý bằng CacheStorage; HTTP cache được trình duyệt quản lý theo HTTP caching semantics.

**9. Vì sao không nên lưu token dài hạn trong IndexedDB?**

JavaScript cùng origin, bao gồm mã XSS, có thể đọc token và gửi ra ngoài. IndexedDB không phải vault chống XSS.

**10. Logout cần làm gì với browser storage?**

Dọn dữ liệu riêng tư và cache thuộc account theo chính sách ứng dụng, xử lý dữ liệu chưa đồng bộ và bảo đảm account khác không nhìn thấy dữ liệu cũ.

## Ghi nhớ

IndexedDB là cơ sở dữ liệu bất đồng bộ cho record có cấu trúc; Cache API lưu các cặp Request/Response để phục vụ tài nguyên phù hợp. Cả hai đều dùng quota của browser storage và có thể bị eviction hoặc bị người dùng xóa. Hãy thiết kế schema và transaction ngắn, theo dõi dung lượng, đồng bộ dữ liệu quan trọng, chỉ cache tài nguyên cần thiết và xem mọi dữ liệu local là có thể bị mã JavaScript cùng origin đọc. Đừng lưu bí mật dài hạn ở client storage chỉ vì API lưu trữ có vẻ tiện lợi.

## Tài liệu tham khảo

- [MDN: IndexedDB API](https://developer.mozilla.org/en-US/docs/Web/API/IndexedDB_API)
- [MDN: Using IndexedDB](https://developer.mozilla.org/en-US/docs/Web/API/IndexedDB_API/Using_IndexedDB)
- [MDN: Storage API](https://developer.mozilla.org/en-US/docs/Web/API/Storage_API)
- [MDN: Storage quotas and eviction criteria](https://developer.mozilla.org/en-US/docs/Web/API/Storage_API/Storage_quotas_and_eviction_criteria)
- [MDN: Cache API](https://developer.mozilla.org/en-US/docs/Web/API/Cache)
- [MDN: CacheStorage](https://developer.mozilla.org/en-US/docs/Web/API/CacheStorage)
- [W3C: Indexed Database API](https://w3c.github.io/IndexedDB/)
