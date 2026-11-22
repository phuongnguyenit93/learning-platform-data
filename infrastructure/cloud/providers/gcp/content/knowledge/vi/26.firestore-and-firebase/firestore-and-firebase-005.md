# Realtime listeners và đồng bộ dữ liệu ứng dụng

Một học viên mở ứng dụng học Java trên điện thoại, đánh dấu bài học đã hoàn thành rồi chuyển sang laptop. Người dùng mong trạng thái xuất hiện gần như ngay lập tức trên cả hai thiết bị, kể cả khi mạng chập chờn. **Cloud Firestore realtime listeners** giúp giao diện tự nhận dữ liệu thay đổi, trong khi **local cache, offline persistence và pending writes** tạo trải nghiệm phản hồi nhanh. Nhưng “realtime” không đồng nghĩa dữ liệu đã được máy chủ xác nhận hoặc mọi xung đột đã được giải quyết đúng nghiệp vụ.

Trong chương **Firestore và Firebase** thuộc module **CLOUD_PROVIDERS_GCP**, bài này nối kiến thức Firebase Authentication, Security Rules, Cloud Run/GKE, IAM và Cloud Monitoring để xây dựng luồng đồng bộ có thể kiểm chứng. Các ví dụ sử dụng **Cloud Firestore, Firebase Web SDK dạng modular** và một ứng dụng danh sách việc học; **Firebase Realtime Database** là sản phẩm khác, không dùng cùng API `onSnapshot()`. Nội dung ưu tiên hành vi **Firestore Core/Standard**; nếu dùng Enterprise/Pipeline operations, phải kiểm tra phạm vi hỗ trợ và mô hình tính giá riêng.

**Sau bài học, bạn có thể:**

1. Lắng nghe thay đổi của **một document** hoặc **query** bằng `onSnapshot()` và dừng lắng nghe đúng vòng đời UI.
2. Phân biệt snapshot đầu tiên, `docChanges()`, `fromCache` và `hasPendingWrites`.
3. Thiết kế hành vi offline, phục hồi kết nối và xử lý cập nhật đồng thời giữa thiết bị.
4. Viết query theo quyền truy cập, kiểm thử Security Rules và tránh listener phạm vi quá lớn.
5. Ước tính document reads/chi phí, theo dõi lỗi và kiểm thử đồng bộ bằng Firebase Emulator.

## 1. Cơ chế realtime của Firestore

Khi client gọi `onSnapshot(refOrQuery, callback)`, SDK thiết lập listener, cung cấp **snapshot trạng thái hiện tại** rồi phát sự kiện khi kết quả thay đổi. SDK có thể trả dữ liệu từ cache trước, sau đó đồng bộ từ server. Với một query, SDK tiếp tục cập nhật các document **thuộc tập kết quả** khi thêm, sửa hoặc bị loại ra khỏi tập đó.

~~~mermaid
sequenceDiagram
    participant A as Web A
    participant C as Local cache A
    participant F as Firestore
    participant B as Web B
    A->>F: Listen query /users/uid/tasks
    C-->>A: Snapshot từ cache nếu có
    F-->>A: Snapshot hiện tại từ server
    B->>F: Ghi task hoàn thành
    F-->>A: Thay đổi task khớp query
    A->>A: Cập nhật UI
    A->>F: Unsubscribe khi rời màn hình
~~~

| Khái niệm | Ý nghĩa | Điều không nên suy ra |
| --- | --- | --- |
| **Document listener** | Theo dõi một document tại path cụ thể. | Không theo dõi cả collection hoặc mọi quan hệ liên quan. |
| **Query listener** | Theo dõi tập document thỏa bộ lọc, thứ tự và giới hạn. | Không phải “đăng ký mọi sự kiện” trong toàn database. |
| **Initial snapshot** | Trạng thái hiện tại được SDK cung cấp khi listener bắt đầu. | Không mặc định là chỉ những thay đổi mới từ lúc mở màn hình. |
| **`docChanges()`** | Các thay đổi `added`, `modified`, `removed` giữa các query snapshots. | `removed` không nhất thiết là document đã bị xóa; có thể không còn khớp query. |
| **`unsubscribe()`** | Dừng nhận sự kiện khi màn hình/component không cần dữ liệu. | Không xóa dữ liệu Firestore và không hủy những write đã gửi. |

### 1.1. Snapshot document và query

Với document listener, kiểm tra `snapshot.exists()` trước khi gọi `snapshot.data()`: một document có thể chưa tồn tại hoặc đã bị xóa. Với query listener, `snapshot.docs` chứa danh sách document đang khớp truy vấn; `snapshot.empty` cho biết tập kết quả rỗng.

**Snapshot đầu của query** thường có thay đổi `added` cho các document hiện có trong tập kết quả. Nếu dùng `docChanges()` để bổ sung từng hàng vào UI mà không phân biệt lần khởi tạo, có thể vô tình thêm trùng. Chọn **một** trong hai cách: dựng lại danh sách từ `snapshot.docs` cho tập nhỏ, hoặc duy trì state theo document ID và áp diff.

### 1.2. Firebase SDK không phải hệ thống phân quyền

Realtime transport chỉ giúp truyền thay đổi. **Firebase Authentication** cung cấp danh tính người dùng; **Firestore Security Rules** xác định quyền đọc/ghi cho mobile/web clients; **IAM** dùng cho server SDK và các dịch vụ quản trị. Một listener chạy được không tự đảm bảo người dùng có quyền đọc document người khác.

Giới hạn quyền phải nằm **trên server qua Rules/IAM**, không chỉ là bộ lọc mà JavaScript dùng để ẩn những hàng không thuộc người dùng.

## 2. Ví dụ Web SDK modular: lắng nghe và dừng đúng lúc

Giả sử dự án Firebase đã được cấu hình, người dùng đã đăng nhập bằng Firebase Authentication. Dữ liệu lưu tại:

~~~text
users/{uid}/tasks/{taskId}
  title: string
  done: boolean
  updatedAt: timestamp
~~~

Mỗi người dùng có subcollection riêng. Đường dẫn này giúp Rules kiểm soát chủ sở hữu, đồng thời query chỉ đọc các việc học của người đó. Không dùng nó như cơ chế phân quyền duy nhất: Rules vẫn phải được cấu hình.

### 2.1. Cấu hình Firebase và kết nối Firestore

~~~javascript
// firebase-client.js — dùng config WEB thật của project được phê duyệt.
import { initializeApp } from "firebase/app";
import { getAuth } from "firebase/auth";
import { getFirestore } from "firebase/firestore";

const app = initializeApp({
  apiKey: "WEB_API_KEY",
  authDomain: "YOUR_PROJECT.firebaseapp.com",
  projectId: "YOUR_PROJECT",
  appId: "YOUR_WEB_APP_ID"
});
export const auth = getAuth(app);
export const db = getFirestore(app);
~~~

**Firebase Web config không phải service account private key**; dù vậy, vẫn cần cấu hình đúng Authorized Domains, App Check nếu phù hợp, Rules và kiểm soát quota. Không đặt service account JSON key, private API secrets hoặc IAM credentials trong bundle frontend.

### 2.2. Lắng nghe một document

~~~javascript
import { doc, onSnapshot } from "firebase/firestore";
import { db } from "./firebase-client.js";

export function listenTask(uid, taskId, render, reportError) {
  const ref = doc(db, "users", uid, "tasks", taskId);
  const unsubscribe = onSnapshot(
    ref,
    (snap) => {
      render(snap.exists()
        ? { id: snap.id, ...snap.data() }
        : null);
    },
    (error) => reportError(error.code)
  );
  return unsubscribe;
}

// Ví dụ: const stop = listenTask(uid, taskId, render, reportError);
// Khi rời trang, gọi stop() để dừng listener.
~~~

Khi Rules từ chối hoặc query không hợp lệ, callback lỗi được gọi và **listener đó sẽ không tiếp tục phát sự kiện**; cần sửa nguyên nhân trước khi đăng ký lại, không retry mù quáng sau `permission-denied`.

### 2.3. Lắng nghe một query có phạm vi và giới hạn

~~~javascript
import {
  collection, query, orderBy, limit, onSnapshot
} from "firebase/firestore";
import { db } from "./firebase-client.js";

export function listenRecentTasks(uid, onData, onError) {
  const tasks = collection(db, "users", uid, "tasks");
  const q = query(tasks, orderBy("updatedAt", "desc"), limit(20));

  return onSnapshot(q, (snapshot) => {
    // Với danh sách nhỏ, dựng lại state đơn giản và an toàn.
    const rows = snapshot.docs.map((d) => ({
      id: d.id, ...d.data()
    }));
    onData(rows);
  }, onError);
}
~~~

Query này chỉ trả **tối đa 20 task** có trường `updatedAt` và được sắp theo thời gian giảm dần. Nếu một task mới trở thành phần tử thứ 20, task cũ có thể bị `removed` khỏi tập kết quả **do thay đổi limit**, dù document đó vẫn tồn tại trong Firestore.

Với ứng dụng React, đăng ký listener trong `useEffect` và **return unsubscribe** ở cleanup khi `uid` thay đổi hoặc component unmount. Không tạo listener trong mỗi lần render hoặc trong callback của chính listener; sẽ tăng số kết nối, số sự kiện và chi phí.

### 2.4. Chỉ áp thay đổi của query bằng `docChanges()`

Khi danh sách lớn và muốn cập nhật phần tử thay vì dựng lại toàn bộ state, có thể xử lý diff theo **document ID**:

~~~javascript
import { onSnapshot } from "firebase/firestore";

// q là query đã tạo ở mục 2.3.
const stateById = new Map();
const stop = onSnapshot(q, (snapshot) => {
  for (const change of snapshot.docChanges()) {
    const id = change.doc.id;
    if (change.type === "removed") {
      stateById.delete(id);
    } else { // added hoặc modified
      stateById.set(id, { id, ...change.doc.data() });
    }
  }
  render([...stateById.values()]);
}, (error) => showError(error.code));
~~~

Đoạn code này là **minh họa thuật toán diff**; `q`, `render` và `showError` phải được truyền từ màn hình gọi, đồng thời phải dọn `stateById` khi thay query hoặc người dùng. Map không tự bảo đảm **thứ tự** theo `orderBy`; nếu UI cần đúng thứ tự, sử dụng `snapshot.docs` hoặc áp `oldIndex/newIndex` của document changes.

## 3. Độ trễ cục bộ: dữ liệu hiển thị trước khi server xác nhận

Khi client cập nhật Firestore, SDK có thể phát sự kiện local ngay cả khi chưa gửi thành công lên server (*latency compensation*). Đây là điểm mạnh cho UX, nhưng phải phân biệt:

| Thuộc tính | `true` nghĩa là | UI nên làm gì |
| --- | --- | --- |
| `snapshot.metadata.hasPendingWrites` | Snapshot có thay đổi cục bộ chưa được server xác nhận. | Hiện “Đang đồng bộ”; không tuyên bố đã lưu thành công. |
| `snapshot.metadata.fromCache` | Snapshot lấy từ local cache, có thể cũ hoặc thiếu dữ liệu. | Hiện “Dữ liệu có thể chưa cập nhật”; không khẳng định đang online. |
| Cả hai là `false` | Không có ghi cục bộ pending trong snapshot và dữ liệu snapshot được lấy từ server. | Có thể hiện trạng thái đồng bộ tại thời điểm snapshot; vẫn không thay cho kết quả giao dịch nghiệp vụ khác. |

Mặc định listener **không phát sự kiện khi chỉ metadata thay đổi**. Bật `includeMetadataChanges: true` nếu UI phải chuyển rõ từ “Đang gửi” sang “Đã đồng bộ” ngay cả khi dữ liệu không đổi.

### 3.1. Theo dõi pending writes và nguồn dữ liệu

~~~javascript
import { doc, onSnapshot } from "firebase/firestore";
import { db } from "./firebase-client.js";

export function watchSyncStatus(uid, taskId, show) {
  const ref = doc(db, "users", uid, "tasks", taskId);
  return onSnapshot(
    ref,
    { includeMetadataChanges: true },
    (snapshot) => show({
      data: snapshot.exists() ? snapshot.data() : null,
      pending: snapshot.metadata.hasPendingWrites,
      fromCache: snapshot.metadata.fromCache
    }),
    (error) => show({ error: error.code })
  );
}
~~~

Ví dụ cập nhật một task:

~~~javascript
import { doc, updateDoc, serverTimestamp } from "firebase/firestore";
import { db } from "./firebase-client.js";

export async function completeTask(uid, taskId) {
  const ref = doc(db, "users", uid, "tasks", taskId);
  // Listener có thể hiển thị 'done: true' trước khi Promise hoàn tất.
  await updateDoc(ref, {
    done: true,
    updatedAt: serverTimestamp()
  });
  // Promise thành công: thao tác ghi được server xác nhận.
}
~~~

Nếu `updateDoc()` bị từ chối (ví dụ Rules không cho phép), SDK sẽ báo lỗi và có thể hoàn nguyên trạng thái hiển thị cục bộ theo kết quả từ server. Hãy **catch lỗi của Promise**, không dùng `hasPendingWrites=false` làm cách duy nhất để kết luận ghi thành công.

**Lưu ý `serverTimestamp()`:** timestamp trong khi đang pending có thể được biểu diễn bằng giá trị tạm, null hoặc giá trị trước đó tùy cách đọc/SDK. Vì vậy UI không được dựa vào một timestamp local tạm thời làm bằng chứng tuyệt đối về thứ tự hoàn tất giao dịch.

### 3.2. Chờ tất cả ghi đã được gửi trước thời điểm gọi

Khi ứng dụng cần hiện “Mọi thay đổi trước thời điểm này đã đồng bộ”, Web SDK có hàm:

~~~javascript
import { waitForPendingWrites } from "firebase/firestore";
import { db } from "./firebase-client.js";

export async function waitForSync() {
  await waitForPendingWrites(db);
}
~~~

Hàm chờ các ghi **đang pending tại thời điểm gọi**, không tự chờ những ghi phát sinh sau đó. Có thể bị từ chối khi **người dùng đăng nhập thay đổi**; khi mất mạng, quá trình chờ có thể kéo dài. Không khóa UI vô hạn: cung cấp trạng thái “Đang chờ mạng” và đường thoát phù hợp.

### 3.3. Phân biệt listener và xác nhận giao dịch

~~~mermaid
sequenceDiagram
    participant UI as Giao diện
    participant SDK as SDK/cache
    participant DB as Firestore server
    UI->>SDK: updateDoc(done=true)
    SDK-->>UI: Snapshot pending=true (optimistic)
    SDK->>DB: Commit write
    alt Được phép và commit thành công
      DB-->>SDK: Ack
      SDK-->>UI: Metadata pending=false
    else Bị từ chối / lỗi
      DB-->>SDK: Error
      SDK-->>UI: Promise reject và trạng thái được đối chiếu
    end
~~~

**Bài học:** “đã thấy ở UI của tôi” khác “đã được Firestore commit” và khác “nghiệp vụ đã xử lý xong”. Với thanh toán, hoàn thành bài thi hay cấp chứng chỉ, nên dùng backend xác thực giao dịch và phản hồi nghiệp vụ rõ ràng, không coi một optimistic snapshot là kết quả cuối.

## 4. Offline persistence và đồng bộ khi có mạng trở lại

Cloud Firestore mobile/web có thể giữ dữ liệu đã truy cập trong cache, cho phép một số read/listen/write khi thiết bị offline. Khi kết nối trở lại, SDK gửi những thay đổi đang chờ và cập nhật listeners. Mức hỗ trợ, cache mặc định và API cấu hình **khác theo nền tảng**.

### 4.1. Web: memory cache và persistent cache

Web SDK modular hiện hành có lựa chọn:

~~~javascript
import { initializeApp } from "firebase/app";
import {
  initializeFirestore,
  memoryLocalCache,
  persistentLocalCache,
  persistentMultipleTabManager
} from "firebase/firestore";

const app = initializeApp(firebaseConfig); // config của dự án lab

// CHỌN MỘT cách ở thời điểm khởi tạo:
const dbMemory = initializeFirestore(app, {
  localCache: memoryLocalCache()
});

// Hoặc, trong một ứng dụng/instance Firebase khác:
// const dbPersistent = initializeFirestore(app, {
//   localCache: persistentLocalCache({
//     tabManager: persistentMultipleTabManager()
//   })
// });
~~~

Hai lựa chọn ở trên **loại trừ nhau trên cùng app instance**: chỉ gọi `initializeFirestore` **một lần**, trước khi sử dụng Firestore. `memoryLocalCache()` là mặc định khi không chỉ định; `persistentLocalCache()` lưu cache qua phiên và có thể cấu hình multi-tab manager khi ứng dụng cần nhiều tab.

**Cảnh báo quyền riêng tư:** persistent cache trên trình duyệt có thể còn tồn tại khi đóng tab và **không tự xóa khi đăng xuất**. Không bật trên kiosk, máy dùng chung hoặc thiết bị không đáng tin mà chưa đánh giá nguy cơ. Nếu ứng dụng thay người dùng trên cùng thiết bị, phải dừng listeners của người dùng cũ, xóa state UI và có chính sách quản lý cache phù hợp; đăng xuất **không đồng nghĩa đã xóa dữ liệu cache khỏi đĩa**.

### 4.2. Xung đột ghi khi hai thiết bị offline

Giả sử điện thoại và laptop cùng sửa trường `title` của một document khi offline, sau đó lần lượt đồng bộ:

- Mỗi thiết bị trước hết thấy **thay đổi cục bộ** của mình.
- Khi kết nối trở lại, các write được gửi lên server; với nhiều thay đổi lên **cùng document**, Firestore dùng cơ chế **last-write-wins**.
- Thiết bị còn lại nhận snapshot mới, có thể khiến tên công việc “đổi lại” so với trạng thái local trước đó.

**Last-write-wins không phải merge nghiệp vụ thông minh.** Đừng cho hai thiết bị cùng sửa một object đơn chứa cả nội dung dài/tiến độ/quyền quan trọng nếu ghi cuối có thể làm mất thay đổi hợp lệ của người khác.

| Nhu cầu | Thiết kế thường hợp lý hơn |
| --- | --- |
| Toggle một cờ độc lập | `updateDoc()` chỉ cập nhật field cần đổi, tránh ghi đè toàn document bằng dữ liệu cũ. |
| Bộ đếm lượt hoàn thành/lượt thích | `increment(1)` khi phù hợp; không đọc–cộng–ghi thủ công trên client. |
| Tập tag | `arrayUnion()`/`arrayRemove()` khi phù hợp semantics, kiểm tra kích thước document. |
| Thay đổi phụ thuộc dữ liệu đang có | **Transaction** khi online, có kiểm tra/giải quyết xung đột. |
| Chỉnh sửa tài liệu cộng tác phức tạp | Thiết kế revision/merge/CRDT hoặc backend điều phối; Firestore listener tự nó không cung cấp thuật toán merge. |
| Ghi nhiều document không cần đọc trước | **Write batch** có tính atomic; mobile/web SDK có thể xếp hàng offline. |

**Transactions của Firestore thất bại khi client offline**; không mô tả transaction như một giải pháp offline-first cho mọi chỉnh sửa. Với nghiệp vụ cần consistency nghiêm ngặt (đặt hàng có tồn kho, thanh toán), dùng backend/Cloud Run với validation, transaction hoặc workflow đáng tin cậy theo yêu cầu.

## 5. Bảo mật listener bằng Authentication và Security Rules

Một query được lắng nghe liên tục vẫn là **read request có kiểm tra quyền**. Security Rules áp dụng cho Web/Apple/Android SDK, bao gồm listener; **server SDK dùng IAM và không chịu Security Rules theo cùng cách**.

### 5.1. Rules cho dữ liệu theo người dùng

Ví dụ tối thiểu cho **project lab**, theo đường dẫn `users/{uid}/tasks/{taskId}`:

~~~javascript
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /users/{userId}/tasks/{taskId} {
      allow read, write: if request.auth != null
                         && request.auth.uid == userId;
    }
  }
}
~~~

Rule cho phép người đã đăng nhập truy cập **chỉ các task trong đường dẫn UID của họ**. Đây là ví dụ về **ownership**, chưa phải rules đầy đủ cho production: cần bổ sung kiểm tra kiểu dữ liệu, độ dài `title`, các field được phép cập nhật, trạng thái hợp lệ, giới hạn kích thước, vai trò quản trị và bảo vệ các document khác. Không áp rule kiểu `allow read, write: if true` lên database có dữ liệu thật.

**Authentication UID phải đến từ Firebase Auth**, không chấp nhận `uid` do client gửi lên như một bằng chứng quyền truy cập. Trước khi đổi tài khoản hoặc đăng xuất, hủy listener cũ và xóa danh sách hiển thị để tránh lộ dữ liệu của tài khoản trước trên cùng thiết bị.

### 5.2. Security Rules không tự lọc query

Giả sử collection chung `tasks` có field `ownerUid` và Rules chỉ cho phép đọc những document có `ownerUid == request.auth.uid`. Client **không được** dùng:

~~~javascript
// SAI: có thể trả task của người khác, nên cả query bị Rules từ chối.
onSnapshot(collection(db, "tasks"), handleSnapshot);
~~~

Phải viết query tương thích với điều kiện Rules:

~~~javascript
import { collection, query, where, onSnapshot } from "firebase/firestore";

const q = query(
  collection(db, "tasks"),
  where("ownerUid", "==", auth.currentUser.uid)
);
const stop = onSnapshot(q, handleSnapshot, handleError);
~~~

Đây là **một mô hình thay thế** cho cấu trúc theo path ở mục 2; không cần tạo cả hai collection trong cùng lab. Rules xét **khả năng query có thể trả tài liệu không được phép**, không duyệt từng document rồi âm thầm lọc những hàng khác UID. Vì vậy query thiếu điều kiện bảo mật có thể bị `permission-denied` dù dữ liệu hiện tại tình cờ chỉ thuộc một user.

### 5.3. Vòng đời đăng nhập và listener

~~~javascript
import { onAuthStateChanged } from "firebase/auth";
import { auth } from "./firebase-client.js";
import { listenRecentTasks } from "./tasks.js";

let stopTasks = null;
const stopAuth = onAuthStateChanged(auth, (user) => {
  stopTasks?.();
  stopTasks = null;
  clearTaskUI();  // Không giữ danh sách của tài khoản trước.

  if (user) {
    stopTasks = listenRecentTasks(
      user.uid,
      renderTasks,
      (error) => showTaskError(error.code)
    );
  }
});

// Khi đóng toàn bộ màn hình:
// stopTasks?.();
// stopAuth();
~~~

`clearTaskUI`, `renderTasks` và `showTaskError` là callback của ứng dụng. Mẫu trên mô tả lifecycle; trong React/Vue cần đặt các thao tác vào hook/cleanup tương ứng. Không chia sẻ một listener có quyền của user A để dùng lại cho user B.

### 5.4. Khi nào cần backend thay vì client listener?

Client listener phù hợp dữ liệu mà user **được phép đọc trực tiếp**. Với kết quả thanh toán, kiểm duyệt, tổng hợp tenant hoặc dữ liệu có logic quyền phức tạp, nên xem xét backend trên Cloud Run/GKE dùng IAM, ghi **projection đã được phép hiển thị** vào Firestore và chỉ listen projection đó. **Không gửi service account key hoặc Admin SDK credential tới trình duyệt.**

## 6. Thiết kế query, hiệu năng và chi phí realtime

Một listener không phải kết nối “miễn phí vô hạn”. Khi bắt đầu, Firestore phải đưa tập kết quả ban đầu tới client; sau đó gửi những thay đổi liên quan. Query lớn sẽ tăng latency khởi tạo, network/memory và số document reads.

### 6.1. Khi nào dùng listener?

| Nhu cầu | Cách tiếp cận | Lý do |
| --- | --- | --- |
| Một task đang mở | `onSnapshot(docRef)` | Chỉ theo dõi document cần hiển thị. |
| 20 task mới nhất của user | `onSnapshot(query(...limit(20)))` | Giới hạn kết quả và tránh listen cả collection. |
| Danh sách lịch sử 100.000 task | Query một lần + pagination bằng cursor | Không tải và giữ 100.000 document trong một listener UI. |
| Báo cáo tổng hợp mỗi giờ | Backend aggregate, cache hoặc one-shot query | Không cần subscribe vào từng thay đổi nhỏ. |
| Dòng sự kiện thay đổi hàng nghìn lần/giây | Đánh giá mô hình đồng bộ khác / tổng hợp theo nhịp | Rủi ro latency, chi phí và churn của tập kết quả. |

**Một query có `limit(20)` không tự giữ nguyên 20 document từ lúc mở:** khi thứ tự thay đổi, một document có thể được thêm vào và một document khác rời tập kết quả, dẫn đến thay đổi đọc và UI. Thêm index cho filter/order khi SDK báo thiếu; index không thay thế Security Rules.

### 6.2. Bản chất chi phí listener

Với **Firestore Standard theo document reads**:

- **Snapshot ban đầu:** các document trả về thường được tính là đọc; còn có quy tắc tối thiểu và index-entry reads theo loại query.
- **Trong khi listen:** document được **thêm hoặc cập nhật** vào tập kết quả có thể phát sinh một lượt đọc; document bị **loại khỏi tập kết quả do dữ liệu thay đổi** cũng bị tính đọc. Xóa document thực sự không bị tính read cho sự kiện bị xóa đó.
- **Reconnect:** khi offline persistence **tắt**, ngắt/rồi kết nối lại có thể bị tính như query mới. Khi persistence **bật**, ngắt trên **30 phút** có thể bị tính như query mới.
- **Rules dùng `get()`/`exists()`** có thể tạo thêm document reads khi đánh giá quyền.

**Ví dụ ước tính đơn giản:** 500 người dùng đồng thời mở màn hình, mỗi listener lúc đầu trả 20 task, có thể phát sinh khoảng **10.000 document reads cho lần tải đầu** (chưa tính index entries, Rules, reconnect và các cập nhật). Nếu mỗi người mở lại màn hình liên tục, số lượt đọc tăng theo số lần khởi tạo lại listener. Đây không phải hóa đơn dự đoán chính xác; cần đối chiếu **edition, bảng giá hiện hành, mức sử dụng và quota**. Firestore Enterprise có cơ chế giá dựa trên **read units/real-time update units** khác Standard.

### 6.3. Cách tối ưu mà không giảm tính đúng đắn

1. Lắng nghe **chỉ khi màn hình cần**; hủy đúng lúc và tránh listener trùng lặp.
2. Dùng filter, `orderBy`, `limit` và cursor, không dùng offset lớn để phân trang lịch sử.
3. Giữ document nhỏ, cập nhật field cần thiết thay vì ghi lại toàn bộ object thường xuyên.
4. Nếu màn hình chỉ cần trạng thái tổng, lưu một **projection/snapshot tóm tắt** được cập nhật đúng nghiệp vụ; không mở listener cho hàng trăm child documents.
5. Hạn chế ghi không cần thiết lên document đang được rất nhiều client theo dõi.
6. Theo dõi usage document reads/writes, index entries và traffic theo tính năng, không tối ưu dựa trên giả định kết nối nhàn rỗi luôn tốn phí.

### 6.4. Realtime ở quy mô lớn: đừng nhầm với event streaming

Firestore realtime query bắt đầu bằng truy vấn lấy dữ liệu hiện tại và sau đó nhận cập nhật từ cơ chế changelog; khi hệ thống cân bằng tải hoặc gặp sự cố tạm, listener có thể cần tái đồng bộ. Vì vậy **query ban đầu phải nhanh** và tập dữ liệu listen nên nhỏ.

Firestore listener phù hợp đồng bộ **trạng thái giao diện**; còn luồng sự kiện nghiệp vụ có throughput lớn, replay/retention độc lập hoặc tích hợp nhiều consumers thường phù hợp Pub/Sub cùng worker xử lý. Hai sản phẩm có thể phối hợp: Pub/Sub xử lý event, backend cập nhật document tổng hợp trong Firestore để client nhận realtime.

## 7. Thực hành: hai thiết bị đồng bộ bằng Firebase Emulator

**Mục tiêu:** thử listener, local writes, offline, reconnect và phân quyền người dùng mà **không tạo document trên Firestore production**. Emulator chạy **trên máy phát triển**, dùng dữ liệu giả và tài khoản thử.

### 7.1. Chuẩn bị

Cần Node.js, npm, Firebase CLI và một thư mục **lab riêng**, không dùng thư mục triển khai production. Trong thư mục đó:

~~~bash
npm install firebase
npm install --global firebase-tools

# Khởi tạo Firestore Rules rồi chọn Authentication và Firestore emulators.
# Chỉ thực hiện trong thư mục LAB mới, không ghi đè cấu hình dự án thật.
firebase init firestore
firebase init emulators

# Chạy đúng 2 emulators đã cấu hình (ports minh họa 8080/9099).
firebase emulators:start --only firestore,auth --project demo-sync-lab
~~~

`firebase init` tạo file cấu hình trong thư mục lab của người chạy; nếu không có quyền npm global install, dùng phương án cài đặt CLI theo chính sách hoặc `npx`. Không kết nối SDK tới project thật khi đang kiểm thử offline/cấp quyền, và kiểm tra port thực tế đã chọn trong `firebase.json` của thư mục lab.

Trong **`firestore.rules` của lab**, dùng quy tắc ở mục 5.1, bảo đảm không có rule công khai ngoài ý muốn. Trên các emulator project, SDK nên trỏ tới cùng project ID `demo-sync-lab` để tránh lệch môi trường.

### 7.2. Cấu hình client dùng emulator

Tạo một trang web thử với module Firebase, rồi kết nối tới emulator **ngay sau khi khởi tạo**, trước mọi thao tác database/Auth:

~~~javascript
import { initializeApp } from "firebase/app";
import {
  getAuth, connectAuthEmulator, signInAnonymously
} from "firebase/auth";
import {
  getFirestore, connectFirestoreEmulator,
  collection, doc, setDoc, updateDoc, onSnapshot,
  serverTimestamp, disableNetwork, enableNetwork
} from "firebase/firestore";

const app = initializeApp({
  apiKey: "demo-key",
  authDomain: "demo-sync-lab.firebaseapp.com",
  projectId: "demo-sync-lab",
  appId: "demo-app"
});
const auth = getAuth(app);
const db = getFirestore(app);
connectAuthEmulator(auth, "http://127.0.0.1:9099");
connectFirestoreEmulator(db, "127.0.0.1", 8080);

// Anonymous user CHỈ trên Auth emulator.
const { user } = await signInAnonymously(auth);
const tasksRef = collection(db, "users", user.uid, "tasks");
const taskRef = doc(tasksRef, "lesson-java-1");

const stop = onSnapshot(
  taskRef,
  { includeMetadataChanges: true },
  (s) => console.log("snapshot", {
    exists: s.exists(),
    data: s.data(),
    pending: s.metadata.hasPendingWrites,
    cache: s.metadata.fromCache
  }),
  (e) => console.error("listen error", e.code)
);

await setDoc(taskRef, {
  title: "Hoan thanh bai Java 1",
  done: false,
  updatedAt: serverTimestamp()
});

// Thử mất mạng chỉ với Firestore SDK, vẫn giữ tab mở:
await disableNetwork(db);
const pending = updateDoc(taskRef, {
  done: true, updatedAt: serverTimestamp()
});
// Không await 'pending' khi còn offline: Promise có thể chờ mãi.
await enableNetwork(db);
await pending; // Đã được backend emulator xác nhận.

// Khi đóng màn hình hoặc kết thúc lab:
stop();
~~~

Đoạn code dùng **top-level await** trong JavaScript module; phải chạy từ trang web dev server/bundler phù hợp với import `firebase/*`, không dán nguyên vào console không hỗ trợ module. Chỉ là mã lab: không triển khai nguyên giá trị `demo-key` ra production. Nếu Emulator chạy port khác, sửa hai hàm `connect*Emulator` trước khi thử.

### 7.3. Bộ kiểm thử mong đợi

| Bước | Thao tác | Dấu hiệu đúng |
| --- | --- | --- |
| 1 | Mở tab, đăng nhập user A và đăng ký listener | Snapshot nhận document rỗng hoặc dữ liệu lab hiện có. |
| 2 | `setDoc` một task rồi mở tab thứ hai cùng UID | Hai phiên thấy trạng thái mới sau khi đồng bộ với emulator. |
| 3 | `disableNetwork` trên một tab rồi `updateDoc` | Tab đó thấy thay đổi cục bộ và `pending=true`. |
| 4 | `enableNetwork` và chờ Promise cập nhật | `pending=false`, tab khác nhận snapshot mới sau khi server xác nhận. |
| 5 | Trên browser profile khác đăng nhập user B | User B **không** đọc được document tại path của user A. |
| 6 | Unsubscribe, sau đó thay đổi dữ liệu từ tab khác | Callback đã dừng không còn cập nhật UI. |
| 7 | Tắt kết nối, sửa cùng field từ hai thiết bị rồi nối lại | Có thể thấy xung đột **last-write-wins**, cần giải quyết ở mức ứng dụng. |

**Hai tab cùng trình duyệt có thể chia sẻ Firebase Auth state**, nên để thử hai **UID khác nhau** hãy dùng browser profile khác hoặc session tách biệt. Khi cần kiểm tra persistent cache, cấu hình nó từ lúc khởi tạo trong **một lab riêng** và xác minh chính sách dữ liệu lưu trên thiết bị. Không dùng thông tin học viên thật để thử cache offline.

### 7.4. Kiểm thử Security Rules

Đặt kết quả mong đợi trước khi chạy:

- User A đọc/ghi task dưới `users/A/tasks`: **allow**.
- User A đọc/ghi dưới `users/B/tasks`: **deny**.
- Không đăng nhập vẫn đọc task cá nhân: **deny**.
- Query rộng qua nhiều người dùng trong mô hình collection chung không ràng buộc owner: **deny**.

Dùng **Rules Unit Testing SDK** hoặc **Emulator UI**/test client để chạy cả ca được phép và bị từ chối. Không kết luận Rules an toàn chỉ vì giao diện không hiển thị nút xem dữ liệu người khác.

### 7.5. Dọn lab

Dừng listener và dev server, tắt Emulator Suite, xóa dữ liệu giả và thư mục test theo chính sách. Emulator mặc định không thay đổi database thật, nhưng **chỉ khi SDK thật sự được kết nối tới emulator trước khi gửi request**. Kiểm tra project ID, hostname và logs; không thực thi xóa collection trong một dự án production để dọn bài tập.

## 8. Runbook lỗi listener và đồng bộ

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Listener trả `permission-denied` | Chưa đăng nhập, sai UID/path, query không chứng minh được quyền | Xem auth state, Security Rules và filter/path; thử Rules Emulator. |
| Listener báo cần index | Query nhiều filter/order chưa có composite index | Tạo index được đề xuất sau review; không mở Rules để “sửa” lỗi index. |
| Tab mới thấy dữ liệu cũ trước dữ liệu mới | Snapshot trả từ cache, mạng yếu hoặc chưa đồng bộ | Hiện `fromCache`, lắng nghe update từ server, không thay cache thành nguồn sự thật tuyệt đối. |
| UI hiển thị “đã lưu” rồi biến mất | Optimistic local write bị server từ chối/ghi đè | Theo dõi Promise lỗi, `hasPendingWrites`, serverTimestamp và conflict policy. |
| Dữ liệu một user còn sau khi logout | Listener/state chưa cleanup; persistent cache còn trên thiết bị | Hủy listener, clear UI, đánh giá chính sách persistent cache trên thiết bị dùng chung. |
| RAM hoặc reads tăng khi điều hướng nhiều lần | Mỗi render/mount tạo thêm listener không hủy | Quản lý một subscription theo query; unsubscribe lúc unmount. |
| `removed` dù document chưa bị xóa | Rời tập kết quả do filter, order hoặc `limit` | Kiểm tra query và diff theo document ID; không chạy xóa DB theo sự kiện UI. |
| Hai thiết bị ghi đè nội dung nhau | Last-write-wins cùng document, thiếu version/merge | Tách field, revision check, transaction khi online hoặc backend giải quyết xung đột. |
| Một màn hình cần tải hàng nghìn docs | Query phạm vi lớn, index hoặc màn hình thiết kế chưa phù hợp | Dùng `limit`, cursor, projection; đo snapshot init latency và số reads. |
| Reconnect thường xuyên làm phí tăng | Listener ngắt/reopen, persistence tắt hoặc offline lâu | Giảm re-subscribe, dùng listeners bền theo màn hình, xem chính sách offline và usage. |

**Trình tự điều tra:** kiểm tra UID/auth và đường dẫn → lỗi SDK → trạng thái cache/pending → query/index/Rules → network/reconnect → usage/billing. Với lỗi `permission-denied`, không thử lại liên tục hoặc tắt Rules; sửa điều kiện quyền và thực hiện kiểm thử âm tính trước khi triển khai.

## 9. Bài tập tình huống

### A — Đồng bộ tiến độ học trên hai thiết bị

Điện thoại mất mạng, học viên đánh dấu một bài `done=true`. Laptop online cũng sửa tiêu đề của cùng task. Khi điện thoại có mạng trở lại, giao diện hai nơi có thể thay đổi thêm lần nữa.

**Yêu cầu:** phân biệt optimistic update với server commit; nêu cách giảm nguy cơ ghi đè nhầm.

**Hướng giải:** hiển thị `hasPendingWrites` và `fromCache`; chỉ thông báo lưu thành công sau Promise write/ack. Cập nhật đúng **field** cần thay đổi thay vì `setDoc` toàn object lấy từ cache cũ; với cùng một field bị hai client thay đổi, cần revision/transaction khi online hoặc giải quyết xung đột theo nghiệp vụ. Không tin timestamp do đồng hồ client tạo.

### B — Dashboard mở quá nhiều listeners

Một trang quản trị tạo listener cho từng task, mỗi lần render tạo thêm listener khác và không hủy khi chuyển trang. Trình duyệt chậm, document reads tăng.

**Yêu cầu:** viết lại chiến lược lắng nghe.

**Hướng giải:** listen **một query có filter/limit** cho danh sách hiện tại, kết hợp `docChanges` hoặc `snapshot.docs`; chỉ listen document đang mở khi cần. Đăng ký trong lifecycle của component, hủy trong cleanup, tránh tạo lại query không cần thiết. Theo dõi query size, số subscriptions và reads trước/sau.

### C — Quyền đọc bị từ chối dù “mọi task đều thuộc tôi”

Rules chỉ cho phép đọc document có `ownerUid == request.auth.uid`, nhưng ứng dụng lắng nghe toàn bộ collection `tasks` rồi lọc theo UID trong JavaScript.

**Yêu cầu:** giải thích lỗi và sửa không làm lộ dữ liệu.

**Hướng giải:** Rules **không phải bộ lọc**. Truy vấn phải bao gồm điều kiện `where("ownerUid", "==", uid)` hoặc chuyển sang subcollection dưới `users/{uid}/tasks` với Rules tương ứng. Kiểm thử user khác không được đọc task của chủ sở hữu.

### D — Xác nhận thanh toán từ pending snapshot

Người dùng bấm “Thanh toán”, ứng dụng trực tiếp set `orders/{id}.paid=true` ở frontend rồi listener hiện “Đã thanh toán”, dù write sau đó bị Security Rules từ chối.

**Yêu cầu:** thiết kế lại luồng an toàn.

**Hướng giải:** backend xác thực payment provider, kiểm tra chữ ký/idempotency và ghi trạng thái server-authoritative; Firestore listener **chỉ hiển thị** trạng thái đã được backend ghi. Không cấp quyền client tùy ý sửa `paid`, không hiển thị optimistic write như bằng chứng giao dịch đã hoàn tất.

### E — Tính sơ bộ chi phí mở màn hình

Mỗi người dùng mở dashboard 4 lần/ngày; mỗi lần tạo query listener trả 25 document, không có cập nhật trong thời gian mở. Có 2.000 người dùng/ngày.

**Yêu cầu:** ước lượng document reads ban đầu theo mô hình đơn giản và nêu yếu tố làm số thực tế khác.

**Hướng giải:** `2.000 × 4 × 25 = 200.000` document reads từ các lần tải ban đầu, **trước** khi xét mức tối thiểu, index entries, security-rule reads, reconnect, cache/persistence và billing edition. Dùng session hợp lý, giới hạn query, tránh listener lặp và kiểm tra số liệu usage thực tế; không giảm quyền hoặc bỏ dữ liệu cần thiết chỉ để tiết kiệm reads.

### F — Offline transaction thất bại

Ứng dụng muốn dùng transaction để trừ một suất đăng ký khóa học ngay khi thiết bị đang offline.

**Yêu cầu:** tại sao thao tác không thể bảo đảm và hướng thay thế?

**Hướng giải:** Firestore transactions **không thành công khi offline**. Có thể ghi một **yêu cầu đặt chỗ đang chờ** bằng cơ chế offline queue nếu business cho phép, nhưng backend phải xử lý đồng thời và xác nhận còn suất trước khi chuyển trạng thái thành “Đã đăng ký”. Không tuyên bố hết tồn kho hay thanh toán đã commit dựa vào dữ liệu local.

## 10. Checklist trước khi triển khai

| Kiểm tra | Tiêu chí đạt |
| --- | --- |
| **Đúng dữ liệu** | Listener chọn đúng doc/query, có limit và index phù hợp; dữ liệu thiếu field `orderBy` được xử lý. |
| **Vòng đời** | Mỗi màn hình dùng số listener cần thiết; unsubscribe khi unmount, đổi tài khoản hoặc đổi query. |
| **Trạng thái đồng bộ** | UI phân biệt cache, pending writes, server acknowledgment và lỗi rejected write. |
| **Offline** | Thiết bị offline vẫn có trải nghiệm hợp lý; xung đột và retry có tiêu chí giải quyết. |
| **Bảo mật** | Firebase Auth + Security Rules có unit tests allow/deny; server SDK dùng IAM tối thiểu. |
| **Quyền riêng tư** | Persistent cache chỉ bật khi phù hợp thiết bị và loại dữ liệu; logout dọn UI state. |
| **Hiệu năng** | Query đầu nhanh, số document trả về nhỏ, đo p95/p99 UI latency và reads/writes. |
| **Độ tin cậy** | Đã thử mất mạng, mở hai tab, đổi user, thiếu index, permission-denied và write conflict. |
| **Nghiệp vụ** | Trạng thái tài chính/đăng ký do thành phần đáng tin cậy xác nhận, không dựa vào optimistic event. |

### Tự kiểm tra

1. **`onSnapshot()` có chỉ trả các thay đổi sau thời điểm đăng ký không?** — Không; listener cung cấp trạng thái ban đầu, sau đó cập nhật.
2. **`docChanges().removed` có chắc document đã bị xóa?** — Không; document cũng có thể không còn khớp query/filter/limit.
3. **`hasPendingWrites=true` xác nhận server đã commit?** — Ngược lại; vẫn có ghi cục bộ chưa được server xác nhận.
4. **`fromCache=false` chứng minh mọi nghiệp vụ liên quan đã hoàn tất?** — Không; chỉ phản ánh trạng thái nguồn snapshot.
5. **Vì sao cần `includeMetadataChanges`?** — Để nhận sự kiện khi chỉ trạng thái metadata như pending/cache thay đổi.
6. **Đăng xuất có tự xóa persistent cache không?** — Không; phải có chính sách cache và thiết bị rõ ràng.
7. **Một transaction Firestore mobile/web có chạy hoàn tất offline không?** — Không.
8. **Security Rules có lọc từng document không được phép ra khỏi query không?** — Không; query có thể bị từ chối toàn bộ.
9. **Firestore server SDK có phụ thuộc Security Rules như client SDK?** — Không; dùng IAM/quyền server.
10. **Vì sao listener lâu dài thường hợp lý hơn mở lại liên tục?** — Giảm những lần chạy lại query ban đầu khi ứng dụng vẫn cần dữ liệu, tùy cache/reconnect/billing.

## 11. Tài liệu chính thức

- [Firestore — Listen to realtime updates](https://firebase.google.com/docs/firestore/query-data/listen): document/query listeners, metadata, `docChanges`, unsubscribe và lỗi.
- [Firestore — Offline access](https://firebase.google.com/docs/firestore/manage-data/enable-offline): memory/persistent cache, đồng bộ lại và last-write-wins.
- [Firestore — Security Rules and queries](https://firebase.google.com/docs/firestore/security/rules-query): vì sao Rules không phải filters, query theo chủ sở hữu.
- [Firestore — Transactions and batched writes](https://firebase.google.com/docs/firestore/manage-data/transactions): atomic writes, transaction retry và offline behavior.
- [Firestore — Understand billing](https://firebase.google.com/docs/firestore/pricing): reads của query listeners, index entries, Rules và reconnect cho Standard.
- [Firestore — Enterprise pricing](https://firebase.google.com/docs/firestore/enterprise/pricing): mô hình read units/real-time updates khi dùng Enterprise.
- [Firestore — Realtime queries at scale](https://firebase.google.com/docs/firestore/real-time_queries_at_scale): query initialization, changelog, large listeners và costs.
- [Firebase Local Emulator Suite](https://firebase.google.com/docs/emulator-suite/install_and_configure): cấu hình Auth/Firestore emulators và project ID.
- [Firestore Web modular API reference](https://firebase.google.com/docs/reference/js/firestore): `onSnapshot`, `waitForPendingWrites`, cache và network controls.
- [Firebase Security Rules testing](https://firebase.google.com/docs/rules/emulator-setup): thử allow/deny bằng emulator trước triển khai.

**Kết luận:** Realtime listeners làm giao diện phản hồi nhanh khi dữ liệu thay đổi, nhưng đồng bộ đúng cần **quản lý vòng đời listener, phân biệt dữ liệu local với server, giải quyết xung đột và áp Security Rules/IAM**. Thiết kế tốt giới hạn tập kết quả, xử lý offline không gây mất dữ liệu, bảo vệ người dùng và được kiểm chứng bằng **lỗi thực tế, độ trễ đồng bộ và document reads**, không chỉ bằng việc thấy UI thay đổi tức thì.
