# Hands-On: Calling Vertex AI Prediction from Java

A Java application on Cloud Run needs to estimate **transaction risk** before deciding whether to require additional verification. A machine learning model is already deployed on a **Vertex AI Endpoint**; the application simply sends feature data, receives a prediction, and applies business rules. To do this right, Java must know the **model's input/output format**, use Application Default Credentials (ADC), call the **right regional endpoint**, handle errors, and never write sensitive data to logs.

This lesson belongs to the **Vertex AI and Machine Learning** chapter in module **CLOUD_PROVIDERS_GCP**: connecting ML workflows with projects/IAM, VPC, Cloud Run/GKE, deployment automation, reliability monitoring, and cost. It covers **online prediction for an already-deployed custom-trained model** via the Java client library; never assume this API is equivalent to Gemini `generateContent`, batch prediction, or Vertex AI Vector Search.

After this lesson, you can:

- Distinguish **Model**, **Endpoint**, **DeployedModel**, `trafficSplit`, and **PredictionService**.
- Inspect a deployment along with input/output schemas using Console/`gcloud` before sending data.
- Build a `PredictRequest` with Protobuf `Value` `instances` and invoke `PredictionServiceClient` from Java 17+.
- Configure the **regional API endpoint**, ADC, and appropriate `aiplatform.endpoints.predict` permissions.
- Parse `PredictResponse.predictions` and `deployedModelId`; protect Java services against input errors, quotas, timeouts, and out-of-schema outputs.
- Distinguish online/batch prediction, public/private endpoints, autoscaling, and deployed compute costs.
- Test against a model with a defined contract, measure p95 latency, manage model versioning/canaries, and monitor drift.

> **Scope:** projects, IDs, and models in this lesson are examples. Run predictions only when you have an **Endpoint with a properly formatted deployed model**; `predict` calls neither train nor deploy models. Creating/deploying endpoints with CPU/GPU resources incurs **continuous costs**; never operate on production without authorization.

## 1. From Model to Prediction Response

~~~mermaid
flowchart LR
  A["Java API / Cloud Run"] --> B["ADC + IAM permission"]
  B --> C["Vertex AI regional PredictionService"]
  C --> E["Endpoint: traffic split"]
  E --> D1["Deployed model v1"]
  E --> D2["Deployed model v2"]
  D1 --> R["PredictResponse"]
  D2 --> R
  R --> F["Java validate score + business decision"]
~~~

| Object | Example | Meaning |
|---|---|---|
| **Model** | `projects/P/locations/L/models/M` | Artifacts/metadata for a model; not necessarily serving online yet |
| **Endpoint** | `projects/P/locations/L/endpoints/E` | Resource apps invoke via `predict` |
| **DeployedModel** | `deployedModelId` | A model version serving on an Endpoint with machine/replica config |
| **Traffic split** | 90% v1, 10% v2 | Routes each prediction request to a DeployedModel |
| **PredictionService** | `L-aiplatform.googleapis.com:443` | API service the Java client connects to over gRPC/TLS |
| **PredictRequest.instances** | Array of JSON/protobuf values | Per-record data matching the serving model contract |
| **PredictResponse.predictions** | Array of predicted values | Structure **defined by the model**, not always a plain float |

**Endpoint ID differs from Model ID.** `gcloud ai models describe` inspects artifacts; `gcloud ai endpoints describe` shows which models are deployed on the Endpoint and their traffic split. An Endpoint can host multiple DeployedModels with a **compatible interface**, though a new model version can break schemas if contracts are not managed strictly.

## 2. Sample Contract: Three Input Features

To keep examples consistent, suppose the ML team delivered a risk classification model with **contract v1**:

| Position | Feature | Type / Unit | Example |
|---|---|---|---:|
| 0 | `amount_minor` | Amount in minor units, non-negative integer | 12500 |
| 1 | `account_age_days` | Account age in days | 365 |
| 2 | `failed_attempts_24h` | Failed login attempts in 24 hours | 0 |

Illustrative input as an **ordered numeric array**; **use this format only when the model was trained/deployed expecting a numeric vector in that exact order**:

~~~json
{
  "instances": [
    [12500, 365, 0],
    [900000, 3, 7]
  ]
}
~~~

Another serving container might require each instance as an **object** like `{"amount_minor":12500,"account_age_days":365,"failed_attempts_24h":0}`, or tensors with custom field names. There is no universal "default Java schema" across all Vertex AI models. Check **`predictSchemata.instanceSchemaUri`, `parametersSchemaUri`, and `predictionSchemaUri`** if declared by the model; for custom containers, inspect docs and the `/predict` handler implementation.

The output is also a **contract**, for example the model *might* return:

~~~json
{
  "predictions": [
    {"risk_score": 0.08},
    {"risk_score": 0.91}
  ],
  "deployedModelId": "DEPLOYED_MODEL_ID"
}
~~~

This is merely a **hypothetical output example**, not a guaranteed response from a real model. A scikit-learn classifier might return scalar/list probabilities, AutoML tabular returns objects with classes/scores, and custom servers can return another structure altogether. Java must validate schemas and output bounds before interpreting `0.91` as a probability and acting on it.

## 3. Preflight: Project, Region, Endpoint, IAM, and Network

Prerequisites: project with billing and Vertex AI API enabled; **model uploaded and deployed to an Endpoint**; `gcloud` CLI; Java 17+; runtime principal with prediction permission. Pick a region supporting the model/infrastructure (e.g., `us-central1` in this lab) complying with residency rules.

~~~bash
PROJECT_ID="my-vertex-risk-lab"
REGION="us-central1"
ENDPOINT_ID="1234567890123456789"   # replace with real endpoint ID

gcloud config set project "$PROJECT_ID"
gcloud services enable aiplatform.googleapis.com --project="$PROJECT_ID"

# Inspect endpoints, deployment state, and traffic split.
gcloud ai endpoints list --project="$PROJECT_ID" --region="$REGION"
gcloud ai endpoints describe "$ENDPOINT_ID" \
  --project="$PROJECT_ID" --region="$REGION" \
  --format="yaml(name,displayName,deployedModels,trafficSplit)"
~~~

**Proceed only if:** the Endpoint exists in `$REGION`, `deployedModels` is non-empty, `trafficSplit` is valid, deployment is ready, and the model/feature contract is confirmed. With a shared public Endpoint, the regional API host and the Endpoint resource name are **two distinct components**, both of which must match. When using **dedicated public/private Endpoints**, the URL/network path may differ—never reuse shared `PredictionServiceClient` assumptions blindly across all endpoint types.

### IAM Permissions Across Identities

| Principal | Function | Permissions to Consider |
|---|---|---|
| **Java runtime SA** | Call predictions only | `aiplatform.endpoints.predict` on matching resource/project (e.g., `roles/aiplatform.user` or narrow custom role) |
| **ML deployer** | Upload models, create Endpoints, deploy versions | Endpoint/Model Admin permissions, `iam.serviceAccounts.actAs` if deploying under a dedicated serving SA |
| **Model serving container SA** | Read secrets/Cloud Storage inside handler if needed | Permissions for resources *the container* accesses, separate from caller SA |
| **SRE** | View latency, errors, endpoint health | Appropriate Monitoring/Logging/Vertex AI read roles |

`roles/aiplatform.user` is often **broader than just predict permission**. Where models/policies support granular IAM, consider a custom role with `aiplatform.endpoints.predict` plus only genuinely required metadata read rights. **Never grant `roles/aiplatform.admin` to a Java API** to fix a 403. Never ship service account JSON keys inside JARs, container images, or Git.

### Local ADC Differs from gcloud CLI Credentials

~~~bash
# On an authorized dev machine only; ADC is distinct from gcloud user login.
gcloud auth application-default login

# Check the project configured for calls without printing access tokens to logs.
gcloud config get-value project
~~~

On Cloud Run/GKE, Java pulls ADC from the **runtime service account** (Cloud Run `--service-account`; GKE via Workload Identity Federation). Permissions held by the human running `gcloud ai endpoints describe` **do not transfer automatically to the runtime service account**.

### Public vs Private Network

Shared public Endpoints are typically reached via `REGION-aiplatform.googleapis.com:443` over HTTPS/gRPC with IAM tokens; workloads need outbound DNS/TLS access to Google APIs. **Private Endpoints** may require VPC/PSC/peering/DNS/custom hostnames and matching client/transport configs in addition to IAM. Holding predict permissions does not create a VPC route; conversely, TCP/TLS reachability does not prove valid IAM or schema responses.

## 4. Smoke Testing with gcloud Before Writing Java

To isolate Java bugs from endpoint/model issues, test a request first using the **exact data and endpoint** Java will call. In a personal lab folder, create `predict-request.json`:

~~~json
{
  "instances": [
    [12500, 365, 0],
    [900000, 3, 7]
  ]
}
~~~

From a terminal authenticated as a principal allowed to call prediction:

~~~bash
gcloud ai endpoints predict "$ENDPOINT_ID" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --json-request=predict-request.json
~~~

This is the current **Vertex AI** command—do not use legacy AI Platform's `gcloud ai-platform predict --model`. This sends two instances; verify the response contains `predictions` matching the **actual model contract**. Every deployed model/serving container can define its own response shape; never assume "0.91 means high risk" if the model returns **logits**, **class labels**, or **probability vectors** in a different order.

If the command fails, classify the error first:

| Symptom | Common Cause |
|---|---|
| `NOT_FOUND` | Wrong project, region, Endpoint ID, or endpoint does not exist |
| `FAILED_PRECONDITION` | Endpoint/model not deployed or deployment not ready |
| `INVALID_ARGUMENT` | JSON missing `instances`, wrong types/shape, schema mismatch, payload too large |
| `PERMISSION_DENIED` | Current principal lacks `aiplatform.endpoints.predict`, org policy/perimeter block |
| `RESOURCE_EXHAUSTED` | Quota, request concurrency, or endpoint capacity limit |
| `UNAVAILABLE`/`DEADLINE_EXCEEDED` | Transient failure, network/latency issue, or overly slow model |

**Limit warning:** the `predict` API enforces request payload limits (roughly **1.5 MB** for online predict in current docs), and valid instance counts also depend on the model/container. `gcloud ai endpoints predict` reads at most **100 instances from a file** in the current CLI. Never cram millions of records into one online request; use batch prediction or chunk within safe limits.

### If No Endpoint Exists Yet

The ML team can create an Endpoint and deploy **an already-uploaded model** with the commands below, **strictly inside a budget-approved lab project**:

~~~bash
MODEL_ID="UPLOADED_MODEL_ID"

gcloud ai endpoints create \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --display-name="risk-score-lab"

# Copy the new ENDPOINT_ID from create/list/describe output.
# Deploy only if the model supports serving on the chosen machine type.
gcloud ai endpoints deploy-model "$ENDPOINT_ID" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --model="$MODEL_ID" \
  --display-name="risk-v1" \
  --machine-type="n1-standard-2" \
  --min-replica-count=1 \
  --max-replica-count=2
~~~

Creating an Endpoint **does not create a model**, and deploying a model takes time. The machine type must be supported by Vertex AI/edition/model; some models require GPUs or custom serving containers. **A minimum replica of 1 can incur continuous charges even with zero requests.** Scale-to-zero applies only to eligible configurations/features—never assume every deployed model scales to zero when idle.

## 5. Creating a Java Project with Maven

This example uses **Java 17+** and `com.google.cloud:google-cloud-aiplatform`. For a reproducible lab build, minimal `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example</groupId>
  <artifactId>vertex-online-predict</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>com.google.cloud</groupId>
      <artifactId>google-cloud-aiplatform</artifactId>
      <version>3.100.0</version>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.14.0</version>
      </plugin>
      <plugin>
        <groupId>org.codehaus.mojo</groupId>
        <artifactId>exec-maven-plugin</artifactId>
        <version>3.5.1</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

`3.100.0` is a library version referenced from API docs at writing time, **not a permanent requirement**. Production should use the Google Cloud Libraries BOM or platform-vetted dependency management, updating versions and running tests before deployment.

### Example Project Structure

~~~text
vertex-online-predict/
├── pom.xml
└── src/main/java/example/
    └── PredictRisk.java
~~~

No need to fetch tokens manually and attach `Authorization` headers: the Java client uses **ADC**, acquires tokens, and opens a gRPC/TLS channel. For custom serving models on shared public Endpoints, the regional gRPC URI is `REGION-aiplatform.googleapis.com:443`. Never hardcode one environment's Project ID/region/endpoint ID into code when the same artifact runs across dev/staging/prod.

## 6. Complete Java: PredictRequest → PredictResponse

`PredictRisk.java` below **compiles** with the Maven project in Section 5, and **calls successfully** only when the Endpoint exists, IAM/network are valid, and the serving model accepts **instances as three-number arrays**. The model must return **object predictions containing a `risk_score` field in [0,1]** for the score parser to succeed.

~~~java
package example;

import com.google.cloud.aiplatform.v1.EndpointName;
import com.google.cloud.aiplatform.v1.PredictRequest;
import com.google.cloud.aiplatform.v1.PredictResponse;
import com.google.cloud.aiplatform.v1.PredictionServiceClient;
import com.google.cloud.aiplatform.v1.PredictionServiceSettings;
import com.google.protobuf.ListValue;
import com.google.protobuf.Value;
import java.io.IOException;
import java.util.ArrayList;
import java.util.List;

public final class PredictRisk implements AutoCloseable {
    private final PredictionServiceClient client;
    private final String endpointResource;

    public PredictRisk(String project, String region, String endpointId)
            throws IOException {
        if (project.isBlank() || region.isBlank() || endpointId.isBlank()) {
            throw new IllegalArgumentException("Missing Vertex AI config");
        }
        PredictionServiceSettings settings = PredictionServiceSettings
            .newBuilder()
            .setEndpoint(region + "-aiplatform.googleapis.com:443")
            .build();
        this.client = PredictionServiceClient.create(settings);
        this.endpointResource = EndpointName
            .ofProjectLocationEndpointName(project, region, endpointId)
            .toString();
    }

    private static Value number(double n) {
        if (!Double.isFinite(n) || n < 0) {
            throw new IllegalArgumentException("Invalid feature number");
        }
        return Value.newBuilder().setNumberValue(n).build();
    }

    // Exactly three features per the model's CONTRACT V1.
    private static Value instance(
            long amountMinor, long accountAgeDays, long failedAttempts) {
        ListValue vector = ListValue.newBuilder()
            .addValues(number(amountMinor))
            .addValues(number(accountAgeDays))
            .addValues(number(failedAttempts))
            .build();
        return Value.newBuilder().setListValue(vector).build();
    }

    private static double score(Value prediction) {
        // Do not assume all models return a score object.
        if (prediction.getKindCase() != Value.KindCase.STRUCT_VALUE) {
            throw new IllegalStateException(
                "Unexpected prediction type: expected object");
        }
        Value field = prediction.getStructValue()
            .getFieldsOrDefault("risk_score", Value.getDefaultInstance());
        if (field.getKindCase() != Value.KindCase.NUMBER_VALUE) {
            throw new IllegalStateException(
                "Model output missing numeric risk_score");
        }
        double result = field.getNumberValue();
        if (!Double.isFinite(result) || result < 0 || result > 1) {
            throw new IllegalStateException("Risk score out of range");
        }
        return result;
    }

    public List<Double> predict(List<Value> instances) {
        if (instances.isEmpty() || instances.size() > 16) {
            throw new IllegalArgumentException("Expected 1..16 instances");
        }
        PredictRequest request = PredictRequest.newBuilder()
            .setEndpoint(endpointResource)
            .addAllInstances(instances)
            .build(); // Send parameters only when required by the serving model.

        PredictResponse response = client.predict(request);
        if (response.getPredictionsCount() != instances.size()) {
            throw new IllegalStateException(
                "Prediction count did not match request");
        }

        // Log only model identity and count; NEVER log raw features.
        System.out.println("Deployed model: "
            + response.getDeployedModelId());
        List<Double> result = new ArrayList<>();
        for (Value item : response.getPredictionsList()) {
            result.add(score(item));
        }
        return List.copyOf(result);
    }

    @Override
    public void close() {
        client.close();
    }

    private static String requiredEnv(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Missing env: " + name);
        }
        return value;
    }

    public static void main(String[] args) throws Exception {
        String project = requiredEnv("VERTEX_PROJECT_ID");
        String region = requiredEnv("VERTEX_REGION");
        String endpointId = requiredEnv("VERTEX_ENDPOINT_ID");

        List<Value> inputs = List.of(
            instance(12500, 365, 0),
            instance(900000, 3, 7));

        try (PredictRisk predictor =
                 new PredictRisk(project, region, endpointId)) {
            List<Double> risks = predictor.predict(inputs);
            for (int i = 0; i < risks.size(); i++) {
                System.out.printf("item=%d risk=%.4f%n", i, risks.get(i));
            }
        }
    }
}
~~~

**Intentional design choices in this code:**

1. `PredictionServiceClient` is **created once and reused**; instantiating a client/gRPC channel per HTTP request inflates latency, socket churn, and resource pressure.
2. `setEndpoint(region + "-aiplatform.googleapis.com:443")` sets the **API host**; `setEndpoint(EndpointName...toString())` on the request sets the **resource path**—never mix them up.
3. `instances` is a `List<Value>`, each `Value` representing one JSON instance. `ListValue` preserves feature order; Protobuf numbers use `double`, so validate precision/scale and input bounds.
4. Omit `parameters` if the model declares none; for models with valid parameters, supply a `Value` matching `parametersSchemaUri`.
5. The `1..16` bound is a **safety limit chosen by this lab app**, not a fixed Vertex AI quota. Production selects batch sizes from payload limits, latency, memory, and server contracts.
6. There is no "assume safe on prediction error" fallback in the demo: callers must enforce fail-open/fail-closed per business policy rather than fabricating fake scores.

### Running in a Development Environment

~~~bash
export VERTEX_PROJECT_ID="my-vertex-risk-lab"
export VERTEX_REGION="us-central1"
export VERTEX_ENDPOINT_ID="1234567890123456789"

# Run only on a workstation with valid ADC.
gcloud auth application-default login
mvn -q compile exec:java \
  -Dexec.mainClass=example.PredictRisk
~~~

In Windows PowerShell, use `$env:VERTEX_PROJECT_ID="..."` instead of `export`. Actual output depends on the deployed model: **there is no fixed expected risk score**. If the `gcloud` smoke test succeeds yet Java throws `Model output missing numeric risk_score`, the parsing code likely **mismatches the output schema**—you do not need extra IAM.

## 7. From CLI to a Java HTTP Service on Cloud Run

In real systems, `PredictRisk` sits behind a **Java Spring Boot/Quarkus/Jakarta REST API**, rather than running `main()` per request. The API receives an authenticated transaction ID, reads features from an authorized source (Cloud SQL/Spanner/Feature Store), and calls Vertex AI:

~~~mermaid
sequenceDiagram
  participant U as App / client
  participant J as Java Cloud Run API
  participant D as Authorized feature source
  participant V as Vertex AI Endpoint
  U->>J: POST /risk-decisions {transactionId}
  J->>D: Fetch transaction + allowed features
  D-->>J: amount_minor, age_days, attempts
  J->>V: Predict(instances)
  V-->>J: predictions + deployedModelId
  J->>J: Validate score + business rules
  J-->>U: Decision/needsReview + modelVersion
~~~

To reuse the class in Section 6, add one small public method directly inside `PredictRisk`:

~~~java
// Add INSIDE class PredictRisk (not a separate class).
public double predictOne(
        long amountMinor, long ageDays, long failedAttempts) {
    return predict(List.of(
        instance(amountMinor, ageDays, failedAttempts))).get(0);
}
~~~

In a web app, initialize `PredictRisk` at startup and **close the client on shutdown**. The Spring Boot controller below is **only an integration layer sketch**, requiring Spring Boot/Web dependencies and DI config beyond the minimal `pom.xml` in Section 5:

~~~java
// Illustrative REST layer: requires a singleton @Bean PredictRisk and Spring Web.
@RestController
@RequestMapping("/api")
public class RiskController {
    private final PredictRisk predictor;

    public RiskController(PredictRisk predictor) {
        this.predictor = predictor;
    }

    @PostMapping("/risk")
    public Map<String, Object> risk(@RequestBody RiskFeatures features) {
        // Production: authenticate caller, authorize transaction/tenant,
        // then fetch features from a trusted source—never trust raw client fields.
        double score = predictor.predictOne(
            features.amountMinor(),
            features.accountAgeDays(),
            features.failedAttempts24h());
        return Map.of("needsReview", score >= 0.8);
    }
}

record RiskFeatures(long amountMinor,
                    long accountAgeDays,
                    long failedAttempts24h) {}
~~~

The `0.8` threshold is an **illustrative value** that the ML/risk team must calibrate using precision, recall, calibration, false-positive/false-negative costs, and fairness. **Never auto-reject financial transactions solely because a model returned a high score**, and never expose raw scores if doing so lets attackers probe the system. This illustrative controller omits authentication, rate limiting, and tenant checks—**never deploy it directly to production**.

### Granting Permissions to the Cloud Run Runtime Service Account

~~~bash
MODEL_PROJECT="my-vertex-risk-lab"
APP_PROJECT="my-risk-api-lab"
REGION="us-central1"
RUN_SA="risk-api@$APP_PROJECT.iam.gserviceaccount.com"

# Assign only when the SA exists, owner approves, and permissions are reviewed.
gcloud projects add-iam-policy-binding "$MODEL_PROJECT" \
  --member="serviceAccount:$RUN_SA" \
  --role="roles/aiplatform.user"
~~~

This predefined role is convenient for illustration, though **potentially broader than prediction alone**. IAM teams should substitute a narrower custom role or resource-level binding when supported. Java on Cloud Run in `APP_PROJECT` still needs valid network/egress connectivity to Vertex AI in `MODEL_PROJECT`; cross-project access does **not happen automatically**.

With a **complete web application image** already built and pushed, for example:

~~~bash
IMAGE="$REGION-docker.pkg.dev/$APP_PROJECT/apps/risk-api:v1"
ENDPOINT_ID="1234567890123456789"

gcloud run deploy risk-api \
  --project="$APP_PROJECT" \
  --region="$REGION" \
  --image="$IMAGE" \
  --service-account="$RUN_SA" \
  --set-env-vars="VERTEX_PROJECT_ID=$MODEL_PROJECT,VERTEX_REGION=$REGION,VERTEX_ENDPOINT_ID=$ENDPOINT_ID" \
  --no-allow-unauthenticated
~~~

**Note:** `gcloud run deploy` simply deploys an existing image; it **does not turn** the Java CLI class in Section 6 into a web server. You need Spring Boot/Web (or an equivalent framework) listening on Cloud Run's `PORT` env var, health checks, and HTTP tests. Even a Cloud Run endpoint blocking unauthenticated callers still needs **transaction/tenant-level authorization**; a caller with `run.invoker` should not automatically inspect every transaction.

## 8. Intentional Error Handling: 4xx Is Not 5xx

Java GAPIC gRPC calls throw `com.google.api.gax.rpc.ApiException`. Inspect the status code to decide whether to **return an error to the caller**, **perform bounded retries**, or **route to manual review**—avoid collapsing everything into a generic HTTP 500.

| gRPC / API Status | Error Category | Handling Strategy |
|---|---|---|
| `INVALID_ARGUMENT` | Missing/invalid features, shape/schema/size error | Return HTTP 400 at API; fix payload/model contract, **do not retry** |
| `NOT_FOUND` | Wrong Endpoint/model ID/region or nonexistent | Check deployment/config; do not retry endlessly |
| `PERMISSION_DENIED`/`UNAUTHENTICATED` | ADC, role, org policy, VPC-SC | Inspect caller principal; never grant Admin to work around |
| `FAILED_PRECONDITION` | Endpoint unready, invalid config | Check deployment/traffic split and readiness |
| `RESOURCE_EXHAUSTED` | Quota/rate limit/capacity | Throttle, backoff + jitter, review quota/capacity |
| `UNAVAILABLE` | Transient network/server issue | Bounded retry if deadline budget remains |
| `DEADLINE_EXCEEDED` | Client or backend processing took too long | Measure end-to-end, verify outcomes/capacity; bounded retry |
| `INTERNAL`/`UNKNOWN` | Internal or serving handler error | Check logs/metrics; retry only if genuinely transient |

**Java error classification** (wrapping the prediction call in the web/service layer):

~~~java
import com.google.api.gax.rpc.ApiException;
import com.google.api.gax.rpc.StatusCode;

try {
    double score = predictor.predictOne(12500, 365, 0);
    System.out.println(score);
} catch (ApiException ex) {
    StatusCode.Code code = ex.getStatusCode().getCode();
    boolean transientError = switch (code) {
        case RESOURCE_EXHAUSTED, UNAVAILABLE, DEADLINE_EXCEEDED -> true;
        default -> false;
    };
    // Production: retry only with budget/deadline,
    // exponential backoff + jitter and maxAttempts; never log PII.
    System.err.println("Vertex prediction failed: " + code
        + ", mayRetry=" + transientError);
    throw ex;
}
~~~

This performs **classification**, not a retry loop. Production should configure deadlines and retry budgets in **client settings/service layers**: e.g., 2–3 attempts, 200 ms → 1 s backoff with jitter, total time well under the API/Cloud Run timeout. Check the SDK's default retry policy for your version; **never stack SDK retries, service mesh retries, and Java HTTP client retries** so one request triggers unexpected multiple inferences.

**Prediction is usually read-only**, yet **not every serving handler is side-effect-free**. A custom container might write to a DB or emit events, so retrying after a timeout can duplicate side effects. Ideally isolate **pure prediction** from business commits: prediction returns a score, while the transaction service enforces its own idempotency key and exactly-once business semantics.

## 9. Online vs Batch Prediction: Do Not Call One Record at a Time Forever

| Scenario | Suitable Approach | Reason |
|---|---|---|
| Java API needs score synchronously in request | **Online prediction** via Endpoint | Optimized for interactive latency/traffic |
| Millions of BigQuery/GCS rows for nightly report | **Vertex AI batch prediction job** if supported | Avoids N HTTP calls; processes batch files/tables |
| Continuous Pub/Sub stream needing scores | Dataflow/Cloud Run consumer → Online Endpoint or streaming pattern | Backpressure, bounded concurrency, deduplication |
| Generative models like Gemini | `generateContent` API / matching SDK | Do not confuse with `PredictRequest.instances` schema |
| Embeddings/ranking/search | Specialized API/model or that model's prediction schema | Vectors, dimensions, and limits differ from classifiers |

**Batch prediction** has its own job/compute lifecycle and GCS/BigQuery inputs/outputs; **do not keep online Endpoint replicas running** just to score 5 million records nightly when the model supports batch directly. Prefer batch prediction whenever per-record latency is not an SLO. If considering serverless online options for low traffic, verify exact scale-to-zero eligibility before deciding.

## 10. Model Versions, Traffic Splits, and Contract Tests

An Endpoint can host two deployed versions for **canarying**. With a 90% v1 / 10% v2 traffic split, any request may be served by either version per routing config, so the response includes `deployedModelId` for traceability. Never attribute a test outcome to v2 merely because the request ran after deploying v2.

**Controlled upgrade process:**

1. Freeze **feature contract v1**: ordering, types, units, missing values, normalizers, and output schema; new model versions sharing the Endpoint must stay compatible.
2. Before rollout, run a **golden dataset** against both v1 and v2 comparing output shape, latency, calibration, and accuracy/fairness; if schemas diverge, use a separate Endpoint/API version.
3. Deploy v2 with vetted machine/quota/replicas and a small traffic slice. Never hardcode `deployedModelId` inside Java business logic.
4. Observe `deployedModelId`, p95/p99, error rates, feature distributions, and business outcomes **per version**.
5. Ramp traffic only as verified data meets SLOs; on incidents, **shift traffic back to v1** with a schema/feature pipeline rollback plan ready.

Inspect Endpoint before and after canarying:

~~~bash
gcloud ai endpoints describe "$ENDPOINT_ID" \
  --project="$PROJECT_ID" --region="$REGION" \
  --format="yaml(deployedModels,trafficSplit)"
~~~

**Model v2 does not have to return identical numbers to v1.** What must stay invariant at the API boundary are the **input/output contract, permissions, interpretability, and business policy thresholds**. Changing models may require recalibrating per-version thresholds; keeping a fixed threshold without checking calibration can spike false positives.

## 11. Observability: Latency, Errors, Model Quality, and Cost

| Layer | What to Measure | Why |
|---|---|---|
| Java API | End-to-end p50/p95/p99, timeouts, 4xx/5xx | Measure user-facing SLOs, not Vertex AI latency alone |
| Vertex AI Endpoint | Prediction request count, error count, inference latency, replica/CPU/GPU utilization | Find serving/quota/autoscaling bottlenecks |
| Model/deployed version | `deployedModelId`, output shape, score distribution, drift/skew | Catch broken versions or distribution shifts |
| Input data | Missing/invalid features, source freshness, schema version | Avoid scoring on missing or mis-scaled inputs |
| Business outcomes | Precision/recall, manual review rate, false positives once labels arrive | Fast latency does not equal model quality |
| Platform/FinOps | Deployed replica-hours, GPU/CPU, network egress, logs, monitoring | Avoid keeping expensive endpoints idle at low traffic |
| Security | IAM policy changes, token/auth failures, suspicious traffic spikes | Detect unauthorized usage |

**Cloud Monitoring and Cloud Logging:** enable endpoint access/container logs as authorized, build dashboards/alerts for p95 latency and 5xx errors, and track replica counts alongside request rates. **Request/response logging** may capture payloads containing sensitive features: review PII, consent, retention, access controls, and log budgets before enabling.

**Model Monitoring:** drift/skew monitoring and request logging capabilities depend on Endpoint/model version, region, model type, and monitor configuration. When ground-truth labels lag by days, build a reconciliation pipeline joining predictions → outcomes by **pseudonymous transaction ID**, without dumping raw amounts/user info into logs just to compute metrics.

### Online Prediction Cost

~~~text
Approximate total cost
  = deployed model compute by machine/replica-hours
  + accelerator/serving resources (if used)
  + prediction usage per billable model/service tier
  + network/egress, logging/monitoring, Cloud Run, feature reads
~~~

For custom models on an Endpoint with `min-replica-count=1`, **the minimum machine keeps running with zero requests** unless an eligible scale-to-zero config is active. Raising max replicas improves peak throughput but raises peak cost and will not reduce p95 if latency comes from preprocessing. Check pricing by **region, model type, machine type, GPU, and endpoint type**, and verify actuals in Cloud Billing.

**Illustrative capacity note:** 50 requests/s, 1 instance/request, 50 ms average latency does not imply "one replica is enough"—you must measure concurrency, queueing, CPU/GPU memory, batching, model size, p95 tail, and cold/warm behavior. Never size replicas from average QPS alone, and never allow infinite retries during overload.

## 12. Layered Testing

| Test Case | Input / Condition | Expected Verification |
|---|---|---|
| **T1 — Golden request** | 2 valid numeric vectors | Two predictions matching output schema; scores in [0,1] |
| **T2 — Negative features** | `amount_minor=-1`, negative age, negative attempts | Java validation rejects **before** RPC |
| **T3 — Wrong feature count** | 2 or 4 elements instead of 3 | Caught by contract test/server validation, never ignored |
| **T4 — Type mismatch** | String inside numeric vector | Serving model rejects or API flags error; no unsafe auto-casting |
| **T5 — Bad output schema** | Model returns scalar or list without `risk_score` | App fails explicitly; never defaults to score 0 |
| **T6 — Wrong region/endpoint** | Endpoint ID from another project/region | `NOT_FOUND` or config error; no infinite retries |
| **T7 — Negative IAM** | Caller SA lacks predict permission | `PERMISSION_DENIED`; never grant broad IAM to bypass |
| **T8 — Quota and timeout** | Mock `RESOURCE_EXHAUSTED` or `DEADLINE_EXCEEDED` | Bounded retries + circuit breaker/bulkhead, latency budget |
| **T9 — Canary** | Endpoint with v1/v2 traffic split | Logs `deployedModelId`, schema remains compatible |
| **T10 — Sensitive data** | Request includes non-contract PII field | Stripped/blocked; logs contain zero raw features/tokens |
| **T11 — Oversized batch** | 17 records | Blocked by **Java lab app limit** without firing RPC |
| **T12 — Java/CLI parity** | Same endpoint, schema, and features | Results match model contract; deterministic models stay within tolerance |

**Unit tests without live Vertex AI:** extract feature → `Value` conversion and `Value` → risk score parsing to test with mock Protobuf objects:

~~~java
// Mock output for parser; requires no endpoint or ADC.
import com.google.protobuf.Struct;
import com.google.protobuf.Value;

Value fake = Value.newBuilder()
    .setStructValue(Struct.newBuilder()
        .putFields("risk_score",
            Value.newBuilder().setNumberValue(0.42).build())
        .build())
    .build();
// Assert: parser returns 0.42, and rejects null/string/out-of-range.
~~~

In Section 6 code, `score()` and `instance()` are `private`. To unit-test them directly, extract both pure functions into a `RiskContract` class with appropriate visibility. Never hit live endpoints in unit tests; reserve integration tests for staging.

### Reliability Questions to Answer

- When prediction fails, does the app **block transactions, require manual review, or fall back to controlled rules**? Policy must be signed off by product/risk.
- On timeout, does the business workflow perform non-model writes? Are **idempotency keys** and durable state in place to prevent double-charging?
- When v2 scores differ from v1, how do you compare matching cohorts/labels and decide rollback?
- Who can update traffic splits, read request logs, deploy new model containers, and adjust threshold policies?
- Will drift/skew monitoring alert if feature distributions shift abruptly, or do alerts cover latency only?

## 13. Incident Investigation Runbook

~~~bash
PROJECT_ID="my-vertex-risk-lab"
REGION="us-central1"
ENDPOINT_ID="1234567890123456789"

# Read-only check of Endpoint/traffic/model deployment.
gcloud ai endpoints describe "$ENDPOINT_ID" \
  --project="$PROJECT_ID" --region="$REGION" \
  --format="yaml(name,deployedModels,trafficSplit)"

# Verify via CLI using saved contract request.
gcloud ai endpoints predict "$ENDPOINT_ID" \
  --project="$PROJECT_ID" --region="$REGION" \
  --json-request=predict-request.json
~~~

**Diagnostic order:** (1) Is a model deployed on the Endpoint? → (2) Are region/API host and resource name right? → (3) Which Java runtime SA is active? → (4) IAM/perimeter/networking → (5) `instances` contract → (6) handler/container/model health → (7) quotas, machines/replicas, timeouts → (8) response parsing and business policy.

| If You See | Do Not | Do Instead |
|---|---|---|
| `403` when Cloud Run calls Vertex AI | Grant Project Owner/Admin | Check runtime SA, `aiplatform.endpoints.predict`, and policies |
| `INVALID_ARGUMENT` | Retry 10 times | Compare JSON/`Value` shape/schema and types |
| Java parsing fails though CLI predict works | Change machine type immediately | Inspect schema metadata, test output shape, never log PII |
| `429` during peak hours | Raise retries infinitely | Throttle, check autoscaling/quotas, backoff and queue |
| High p95 right after deploying new model | Ignore because mean looks low | Split metrics by `deployedModelId`; measure CPU/GPU/cold starts |
| Costs rise with zero traffic | Delete a production Endpoint | Review min replicas/deployments; shut down **lab** per owner |

## 14. Checklist for Bringing Java Prediction to Production

- [ ] Model uploaded and **deployed to an Endpoint**, `trafficSplit` verified; project/region/Endpoint ID externalized in config.
- [ ] Contract v1 specifies feature order/types/units, missing-value handling, and output semantics, backed by a golden dataset.
- [ ] `PredictRequest.instances` passes valid `Value` lists without confusing scalar/object/list outputs.
- [ ] `PredictionServiceSettings` targets the exact regional API host for the Endpoint type.
- [ ] Java client is a singleton/reused, closed on shutdown, with tuned HTTP/gRPC deadlines and max concurrency.
- [ ] Uses ADC from runtime SA with least-privilege role; zero access tokens or JSON keys in source/logs.
- [ ] Distinguishes online Endpoints, batch prediction, and `generateContent` APIs for generative models.
- [ ] `INVALID_ARGUMENT`/`NOT_FOUND`/`403` are never blindly retried; `429`/`503`/timeouts use bounded retry budgets.
- [ ] Raw customer features/PII are never logged; request/response logging configs passed privacy review.
- [ ] HTTP controller enforces authentication, tenant authorization, rate limits, and source data validation.
- [ ] SLOs cover p95/p99, errors/quotas, model version tracing, and drift/skew/business outcome evaluation.
- [ ] Canary v2 includes traffic splits/rollback and verified input-output contract compatibility.
- [ ] Billing budgets and owners track deployed replica-hours, GPUs, and request volume.
- [ ] Lab resources cleaned up when unused; **undeploy models before deleting an Endpoint** after confirming zero traffic.

## 15. Applied Exercises

**Exercise 1 — Endpoint contract.** Distinguish `Model`, `Endpoint`, `DeployedModel`, and API host. Why does passing `Model ID` instead of `Endpoint ID` in `PredictRequest.endpoint` fail?

**Exercise 2 — Java Value.** Convert JSON instance `[12500,365,0]` into a `Value` wrapping a `ListValue` as shown. Write an alternative using `Struct` when the model expects an object with three named fields.

**Exercise 3 — IAM.** Java on Cloud Run in project A calls an Endpoint in project B. Identify the runtime SA, where `aiplatform.endpoints.predict` is granted, why Admin must not be used, and how deployer SA differs from model container SA.

**Exercise 4 — Gcloud parity.** Against a real lab Endpoint, run `gcloud ai endpoints predict --json-request`, then Java with the exact same input. Compare `predictions`, `deployedModelId`, model version, and reasons outputs might differ.

**Exercise 5 — Parsing.** Suppose real predictions return a list `[0.08,0.92]` or object `{"classes":["safe","risk"],"scores":[0.08,0.92]}`. Update the parser to check class ordering and bounds; explain why the current parser must reject them.

**Exercise 6 — Retries.** Traffic hits 1,000 requests/minute and Vertex AI returns 429 on 20%. Propose a retry budget, max concurrency, rate limit, and circuit breaker so 1,000 requests do not amplify into a retry storm.

**Exercise 7 — Model canary.** Endpoint v1 has p95 120ms; v2 has p95 350ms with fewer false negatives. Propose metrics and a canary/rollback decision workflow rather than comparing average accuracy alone.

**Exercise 8 — PII.** The risk model needs account age and failed attempts; a developer wants to add email/street address because it "might help the model." Draft a policy covering feature minimization, logging/retention, permissions, and fairness review before changing the contract.

**Exercise 9 — Choosing batch.** 8 million records need scoring nightly without real-time needs. Compare cost, throughput, and design of a Vertex batch prediction job versus firing 8 million online requests from Java.

**Exercise 10 — Runbook.** Cloud Run works locally yet returns `PERMISSION_DENIED` in the cloud; after deploying v2, the app throws `Model output missing numeric risk_score`. List separate step-by-step diagnostics for both failures.

## Official Reference Documentation

- [Vertex AI: online predictions for custom-trained models](https://cloud.google.com/vertex-ai/docs/predictions/get-online-predictions) — instances, Endpoints, and response contracts.
- [Java Predict custom-trained model sample](https://cloud.google.com/vertex-ai/docs/samples/aiplatform-predict-custom-trained-model-sample) — `PredictionServiceClient`, `PredictRequest`.
- [PredictionServiceClient Java reference](https://cloud.google.com/java/docs/reference/google-cloud-aiplatform/latest/com.google.cloud.aiplatform.v1.PredictionServiceClient) — predict methods.
- [PredictionServiceSettings Java reference](https://cloud.google.com/java/docs/reference/google-cloud-aiplatform/latest/com.google.cloud.aiplatform.v1.PredictionServiceSettings) — regional host, credentials, and retries.
- [EndpointName Java reference](https://cloud.google.com/java/docs/reference/google-cloud-aiplatform/latest/com.google.cloud.aiplatform.v1.EndpointName) — resource name by project/region.
- [gcloud ai endpoints predict](https://cloud.google.com/sdk/gcloud/reference/ai/endpoints/predict) — JSON smoke testing.
- [gcloud ai endpoints deploy-model](https://cloud.google.com/sdk/gcloud/reference/ai/endpoints/deploy-model) — model serving, replicas.
- [Endpoint types](https://cloud.google.com/vertex-ai/docs/predictions/choose-endpoint-type) — shared/dedicated public/private endpoints.
- [Vertex AI IAM permissions](https://cloud.google.com/iam/docs/roles-permissions/aiplatform) — `aiplatform.endpoints.predict`.
- [Vertex AI batch prediction](https://cloud.google.com/vertex-ai/docs/predictions/get-batch-predictions) — when online latency is unnecessary.
- [Cloud Run service identity](https://cloud.google.com/run/docs/securing/service-identity) — runtime SA and ADC.
- [Google Cloud ADC](https://cloud.google.com/docs/authentication/application-default-credentials) — local and workload authentication.
- [Vertex AI pricing](https://cloud.google.com/vertex-ai/pricing) — serving resources, prediction, and regional costs.
